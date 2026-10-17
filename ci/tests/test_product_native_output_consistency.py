"""Signed synthetic K/R consistency fixtures, never real compiler/host evidence."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.aggregate import verified_index_content, verify_immutable_product_indexes
from ci.products.c_abi import STRICT_CONSUMERS
from ci.products.contract_projection import verify_contract_component_projection
from ci.products.index import IndexEntrySource, build_product_index
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, snapshot_regular_tree,
)
from ci.products.plan import verify_build_key_output_consistency
from ci.products.sdk_runtime_content import verify_native_runtime_projection
from ci.tests.product_chain_variants import _CONSUMER_ROOT, build_variants
from ci.tests.test_product_native_chain import build_chain


class NativeRuntimeOutputConsistencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="native-output-consistency-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chains = {
            name: build_chain(cls.root / name, run, include_bootstrap=True)
            for name, run in (("left", 181), ("right", 182))
        }
        cls.contracts = {}
        cls.proofs = {}
        cls.receipts = {}
        for name, chain in cls.chains.items():
            contract = chain["contract"]
            cls.contracts[name] = verify_contract_component_projection(
                contract["payload"].parent.parent, contract["receipt"], contract["attestation"],
                contract["signature"], chain["context"]["public_key"],
                expected_trust_domain="development", expected_contract_version="0.2.0",
                required_components=("common", "macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64"),
            )
            for target in ("macos-arm64", "linux-x64"):
                arguments = cls.arguments(name, target)
                cls.proofs[name, target] = verify_native_runtime_projection(**arguments)
                cls.receipts[name, target] = load_canonical_json_bytes(
                    arguments["phase_receipts"]["validation"].read_bytes())

    @classmethod
    def arguments(cls, name, target, variants=None):
        chain = cls.chains[name]
        variants = variants or chain["variants"]
        return dict(
            target=target, runtime_stage_root=variants["stages"],
            phase_receipts=variants["variant_phase_receipts"][target],
            variant_payload=variants["variant_bundles"][target],
            attestation=variants["variant_attestations"][target],
            signature=variants["variant_attestation_signatures"][target],
            public_key=variants["variant_public_keys"][target],
            contract_projection=cls.contracts[name], contract_payload=chain["contract"]["payload"],
            required_trust_domain="development",
        )

    @staticmethod
    def receipt_sha(receipt):
        return sha256_bytes(canonical_json_bytes(receipt))

    def index(self, name, target, receipt=None):
        receipt = receipt or self.receipts[name, target]
        context = self.chains[name]["context"]
        producer = context["producer"]
        artifact = next(item["relativePath"] for item in receipt["outputs"]
                        if item["relativePath"].startswith("outputs/native/desktop-runtime-")
                        and item["relativePath"].endswith(".json"))
        return build_product_index(
            [IndexEntrySource(canonical_json_bytes(receipt), artifact)],
            repository=producer["repository"],
            context={"kind": "pull-request", **{key: producer[key] for key in
                     ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
            trust_domain="development", signing=context["signing"], producer=producer,
            stable_history=None,
        )

    def test_independent_signed_raw_producers_compare_equal_without_rewriting_originals(self):
        for target in ("macos-arm64", "linux-x64"):
            with self.subTest(target=target):
                left, right = (self.receipts[name, target] for name in ("left", "right"))
                self.assertEqual(left["buildKey"], right["buildKey"])
                self.assertNotEqual(left["producer"], right["producer"])
                self.assertNotEqual(left["outputs"], right["outputs"])
                proofs = {self.receipt_sha(self.receipts[name, target]): self.proofs[name, target]
                          for name in ("left", "right")}
                before_receipts = [canonical_json_bytes(value) for value in (left, right)]
                before_stages = [regular_file_inventory(self.chains[name]["variants"]["stages"] / target)
                                 for name in ("left", "right")]
                inventories = [proofs[self.receipt_sha(value)].output_inventory(self.receipt_sha(value), value["outputs"])
                               for value in (left, right)]
                self.assertEqual(inventories[0], inventories[1])
                with self.assertRaises(ValueError):
                    verify_build_key_output_consistency([left, right])
                verify_build_key_output_consistency(
                    [left, right], native_runtime_projection=lambda value: proofs[self.receipt_sha(value)])
                indexes = [self.index(name, target) for name in ("left", "right")]
                before_indexes = [canonical_json_bytes(value) for value in indexes]
                callback = lambda entry: proofs[entry["receiptSha256"]]
                views = [verified_index_content(index["entries"][0], native_runtime_projection=callback)
                         for index in indexes]
                self.assertEqual(views[0]["outputs"], views[1]["outputs"])
                self.assertEqual(views[0]["outputInventoryDigest"], views[1]["outputInventoryDigest"])
                with self.assertRaises(ValueError):
                    verify_immutable_product_indexes(*indexes)
                verify_immutable_product_indexes(*indexes, native_runtime_projection=callback)
                self.assertEqual(before_indexes, [canonical_json_bytes(value) for value in indexes])
                self.assertEqual(before_receipts, [canonical_json_bytes(value) for value in (left, right)])
                self.assertEqual(before_stages, [regular_file_inventory(self.chains[name]["variants"]["stages"] / target)
                                                for name in ("left", "right")])

    def test_proof_rejects_other_receipt_output_and_target(self):
        receipt = self.receipts["left", "linux-x64"]
        proof = self.proofs["left", "linux-x64"]
        changed = copy.deepcopy(receipt["outputs"])
        changed[0]["sha256"] = "sha256:" + "f" * 64
        for digest, outputs in ((self.receipt_sha(self.receipts["right", "linux-x64"]), receipt["outputs"]),
                                (self.receipt_sha(receipt), changed)):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                proof.output_inventory(digest, outputs)
        entry = self.index("left", "linux-x64")["entries"][0]
        for changed_entry in (
            {**entry, "target": "macos-arm64", "component": "macos-arm64"},
            {**entry, "receiptSha256": self.receipt_sha(self.receipts["right", "linux-x64"])},
            {**entry, "outputs": changed},
        ):
            with self.assertRaises(ValueError):
                verified_index_content(changed_entry, native_runtime_projection=lambda _: proof)

    def test_wrong_or_unverified_callbacks_cannot_bypass_conflicting_raw_outputs(self):
        receipts = [self.receipts[name, "linux-x64"] for name in ("left", "right")]
        indexes = [self.index(name, "linux-x64") for name in ("left", "right")]
        for returned in (None, {}, object(), self.proofs["left", "macos-arm64"], self.proofs["left", "linux-x64"]):
            with self.subTest(proof_type=type(returned).__name__):
                callback = lambda _, value=returned: value
                with self.assertRaises((ValueError, TypeError)):
                    verify_build_key_output_consistency(receipts, native_runtime_projection=callback)
                with self.assertRaises((ValueError, TypeError)):
                    verify_immutable_product_indexes(*indexes, native_runtime_projection=callback)

    def test_fresh_signed_meaningful_consumer_change_still_conflicts(self):
        # Change actual copied reference source, then build all original receipts
        # and real development signatures normally. No verifier or token is mocked.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sources = root / "consumer"
            snapshot_regular_tree(_CONSUMER_ROOT, sources)
            source = sources / min(STRICT_CONSUMERS)
            source.write_bytes(source.read_bytes() + b"\n/* S786 synthetic meaningful source mutation */\n")
            chain = self.chains["left"]
            with patch("ci.tests.product_chain_variants._CONSUMER_ROOT", sources):
                variants = build_variants(root / "variants", chain["contract"], chain["context"], include_bootstrap=True)
            arguments = self.arguments("left", "macos-arm64", variants)
            changed_proof = verify_native_runtime_projection(**arguments)
            changed = load_canonical_json_bytes(arguments["phase_receipts"]["validation"].read_bytes())
            original = self.receipts["left", "macos-arm64"]
            self.assertEqual(original["buildKey"], changed["buildKey"])
            proofs = {self.receipt_sha(original): self.proofs["left", "macos-arm64"],
                      self.receipt_sha(changed): changed_proof}
            self.assertNotEqual(
                proofs[self.receipt_sha(original)].output_inventory(self.receipt_sha(original), original["outputs"]),
                changed_proof.output_inventory(self.receipt_sha(changed), changed["outputs"]),
            )
            with self.assertRaises(ValueError):
                verify_build_key_output_consistency([original, changed],
                    native_runtime_projection=lambda value: proofs[self.receipt_sha(value)])
            with self.assertRaises(ValueError):
                verify_immutable_product_indexes(self.index("left", "macos-arm64"),
                    self.index("left", "macos-arm64", changed),
                    native_runtime_projection=lambda entry: proofs[entry["receiptSha256"]])


if __name__ == "__main__":
    unittest.main()
