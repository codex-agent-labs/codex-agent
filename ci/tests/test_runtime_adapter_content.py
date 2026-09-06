"""Signed synthetic adapter content closure, never hosted execution acceptance."""

import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ci.products import index as product_index
from ci.products.aggregate import verified_index_content, verify_immutable_product_indexes
from ci.products.index import (
    IndexEntrySource, SignedProductIndex, build_product_index,
    verify_adapter_runtime_index_object, verify_signed_product_index, write_signed_product_index,
)
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, snapshot_regular_tree,
)
from ci.products.registry import PhaseInstanceId
from ci.products.plan import verify_build_key_output_consistency
from ci.products.restore import store_local_object
from ci.products.reuse import LookupSession, RemoteCatalog
from ci.products.runtime_adapter_content import verify_runtime_adapter_projection
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.test_product_native_chain import build_chain


class RuntimeAdapterContentTest(unittest.TestCase):
    components = ("jvm", "node-js", "node-wasm")
    target = "linux-x64"

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="signed-adapter-content-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chains = {}
        for name, run in (("left", 211), ("right", 212), ("changed", 213)):
            private_key, public_key, signing = generate_development_key(cls.root / f"{name}-keys")
            context = {
                "private_key": private_key, "public_key": public_key, "signing": signing,
                "adapter_raw_closure": True,
                "adapter_package_suffix": b"changed package\n" if name == "changed" else b"",
                "producer": {
                    "repository": "codex-agent-labs/codex-agent",
                    "workflowPath": ".github/workflows/product-validation.yml",
                    "commit": f"{run:040x}", "tree": f"{run + 100:040x}",
                    "event": "pull_request", "runId": run, "runAttempt": 1, "pullRequest": 31,
                },
            }
            cls.chains[name] = build_chain(
                cls.root / name, run, context=context,
                variants=None if name == "left" else cls.chains["left"]["variants"],
            )

    def setUp(self):
        self.original = regular_file_inventory(self.root, allow_empty=True)
        self.addCleanup(lambda: self.assertEqual(self.original, regular_file_inventory(self.root, allow_empty=True)))
        temporary = tempfile.TemporaryDirectory(prefix="adapter-content-mutations-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()

    def receipt(self, chain, component):
        path = next(record["receipt"] for record in chain["adapters"]["adapter_receipts"]
                    if (record["component"], record["phase"], record["target"]) ==
                    (component, "validation", self.target))
        raw = path.read_bytes()
        return path, load_canonical_json_bytes(raw), raw

    @staticmethod
    def identity(receipt):
        return {key: receipt[key] for key in ("product", "component", "phase", "target", "productVersion", "buildKey")}

    def arguments(self, chain, component):
        source = chain["compatibility_args"]
        aggregate_inputs = {
            key: source[key] for key in (
                "contract_payload", "contract_metadata_receipt", "contract_attestation",
                "contract_attestation_signature", "contract_public_key", "required_trust_domain",
            )
        }
        for field, source_field in (
            ("aggregate_metadata_receipt", "runtime_metadata_receipt"),
            ("aggregate_attestation", "runtime_attestation"),
            ("aggregate_attestation_signature", "runtime_attestation_signature"),
            ("aggregate_public_key", "runtime_public_key"),
        ):
            aggregate_inputs[field] = source[source_field]
        aggregate_inputs.update({key: chain["variants"][key] for key in (
            "variant_bundles", "variant_phase_receipts", "variant_attestations",
            "variant_attestation_signatures", "variant_public_keys", "variant_validation_evidence",
        )})
        aggregate_inputs.update({key: chain["adapters"][key] for key in (
            "adapter_receipts", "adapter_report_files", "runtime_maven_files", "adapter_evidence",
        )})
        stages = chain["adapters"]["phase_stages"]
        return {
            "aggregate_manifest": chain["aggregate"], "aggregate_inputs": aggregate_inputs,
            "adapter_package_stage": stages[PhaseInstanceId("runtime", component, "package", component)],
            "native_package_stage": chain["variants"]["stages"] / self.target / "package",
            "validation_stage": stages[PhaseInstanceId("runtime", component, "validation", self.target)],
            "distribution_manifest": chain["adapters"]["distribution_manifest"],
        }

    def inventory(self, proof, receipt, raw):
        return proof.output_inventory(sha256_bytes(raw), receipt["outputs"], identity=self.identity(receipt))

    def signed_index_and_object(self, name, component):
        chain = self.chains[name]
        path, receipt, raw = self.receipt(chain, component)
        context = chain["context"]
        producer = context["producer"]
        index = build_product_index(
            [IndexEntrySource(raw, receipt["outputs"][0]["relativePath"])],
            repository=producer["repository"],
            context={"kind": "pull-request", **{key: producer[key] for key in
                     ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
            trust_domain="development", signing=context["signing"], producer=producer, stable_history=None,
        )
        manifest = self.work / f"{name}-{component}-index.json"
        manifest.write_bytes(canonical_json_bytes(index))
        signature = sign_manifest(manifest, context["private_key"], context["signing"])
        verified, original = verify_signed_product_index(SignedProductIndex(manifest, signature), context["public_key"])
        self.assertEqual(canonical_json_bytes(index), original)
        archive = store_local_object(self.arguments(chain, component)["validation_stage"], path,
                                     self.work / f"{name}-{component}-objects")["path"]
        return verified, archive, receipt

    def test_actual_retained_objects_and_signed_indexes_normalize_only_with_bound_proofs(self):
        for component in self.components:
            with self.subTest(component=component):
                originals = {name: self.signed_index_and_object(name, component) for name in ("left", "right")}
                indexes = [originals[name][0] for name in ("left", "right")]
                receipts = [originals[name][2] for name in ("left", "right")]
                self.assertEqual(receipts[0]["buildKey"], receipts[1]["buildKey"])
                self.assertNotEqual(receipts[0]["outputs"], receipts[1]["outputs"])
                before = regular_file_inventory(self.work)
                proofs = {}
                for name, (index, archive, _) in originals.items():
                    entry = index["entries"][0]
                    def original_provider(actual_entry, actual_archive, original_name=name):
                        self.assertEqual(originals[original_name][0]["entries"][0], actual_entry)
                        self.assertEqual(originals[original_name][1], actual_archive)
                        return verify_runtime_adapter_projection(
                            component, self.target, **self.arguments(self.chains[original_name], component))
                    proofs[entry["receiptSha256"]] = verify_adapter_runtime_index_object(entry, archive, original_provider)
                entry_provider = lambda entry: proofs[entry["receiptSha256"]]
                with self.assertRaises(ValueError):
                    verify_build_key_output_consistency(receipts)
                verify_build_key_output_consistency(
                    receipts, adapter_runtime_projection=lambda receipt: proofs[sha256_bytes(canonical_json_bytes(receipt))])
                with self.assertRaises(ValueError):
                    verify_immutable_product_indexes(*indexes)
                verify_immutable_product_indexes(*indexes, adapter_runtime_projection=entry_provider)
                views = [verified_index_content(index["entries"][0], adapter_runtime_projection=entry_provider)
                         for index in indexes]
                self.assertEqual(views[0]["outputs"], views[1]["outputs"])
                self.assertEqual(views[0]["outputInventoryDigest"], views[1]["outputInventoryDigest"])
                self.assertEqual(before, regular_file_inventory(self.work))

    def test_missing_corrupt_crosspaired_or_wrong_identity_object_rejects_before_provider(self):
        left, archive, _ = self.signed_index_and_object("left", "jvm")
        _, other_archive, _ = self.signed_index_and_object("right", "jvm")
        entry = left["entries"][0]
        corrupt = self.work / "corrupt.zip"
        corrupt.write_bytes(b"not an original retained object")
        for supplied in (self.work / "missing.zip", corrupt, other_archive):
            provider = Mock()
            with self.subTest(supplied=supplied), self.assertRaises(ValueError):
                verify_adapter_runtime_index_object(entry, supplied, provider)
            provider.assert_not_called()
        for field in self.identity(entry):
            provider = Mock()
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_adapter_runtime_index_object({**entry, field: "different"}, archive, provider)
            provider.assert_not_called()

    def test_unverified_or_other_original_proof_cannot_admit_object_or_relax_comparison(self):
        left, archive, left_receipt = self.signed_index_and_object("left", "jvm")
        right, _, right_receipt = self.signed_index_and_object("right", "jvm")
        right_proof = verify_runtime_adapter_projection("jvm", self.target, **self.arguments(self.chains["right"], "jvm"))
        for result in (None, {}, object(), right_proof):
            with self.subTest(result_type=type(result).__name__):
                with self.assertRaises(ValueError):
                    verify_adapter_runtime_index_object(left["entries"][0], archive, lambda *_: result)
                with self.assertRaises(ValueError):
                    verified_index_content(left["entries"][0], adapter_runtime_projection=lambda _: result)
                with self.assertRaises(ValueError):
                    verify_build_key_output_consistency([left_receipt, right_receipt], adapter_runtime_projection=lambda _: result)
                with self.assertRaises(ValueError):
                    verify_immutable_product_indexes(left, right, adapter_runtime_projection=lambda _: result)

    def test_signed_catalog_lookup_preserves_original_receipt_and_requires_both_objects(self):
        # Synthetic release-signed promoted-main index for comparison only.
        # Actual restore uses the original development same-PR receipt, not a
        # claim that these fixtures passed any release or hosted execution gate.
        left, left_archive, left_receipt = self.signed_index_and_object("left", "jvm")
        right, right_archive, right_receipt = self.signed_index_and_object("right", "jvm")
        context = self.chains["left"]["context"]
        signing = {**context["signing"], "trustDomain": "release", "keyId": "adapter-catalog-fixture"}
        keys = self.work / "release-keys"
        keys.mkdir()
        (keys / "adapter-catalog-fixture.pub").write_bytes(context["public_key"].read_bytes())
        keyring = self.work / "release-keyring.json"
        keyring.write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "namespace": signing["namespace"], "algorithm": signing["algorithm"],
            "trustDomain": "release", "activeKey": {"keyId": signing["keyId"], "fingerprint": signing["fingerprint"]},
            "retiredKeys": [],
        }))
        producer = {**context["producer"], "event": "push", "pullRequest": None}
        promoted_index = {**left, "signing": signing, "trustDomain": "release", "producer": producer,
                          "context": {"kind": "promoted-main", "commit": producer["commit"], "tree": producer["tree"],
                                      "promotionRunId": producer["runId"], "promotionRunAttempt": producer["runAttempt"]}}
        manifest = self.work / "promoted-jvm-index.json"
        manifest.write_bytes(canonical_json_bytes(promoted_index))
        signature = sign_manifest(manifest, context["private_key"], signing)
        promoted = RemoteCatalog(manifest, signature, {left_receipt["buildKey"]: left_archive},
                                 keyring=keyring, keys_directory=keys)
        same_pr = RemoteCatalog(self.work / "right-jvm-index.json", self.work / "right-jvm-index.sig",
                                {right_receipt["buildKey"]: right_archive},
                                public_key=self.chains["right"]["context"]["public_key"])
        originals = {index["entries"][0]["receiptSha256"]: (name, archive)
                     for name, index, archive in (("left", left, left_archive), ("right", right, right_archive))}
        calls = []
        def callback(entry, archive):
            name, expected_archive = originals[entry["receiptSha256"]]
            self.assertEqual(expected_archive, archive)
            calls.append(name)
            return verify_runtime_adapter_projection("jvm", self.target, **self.arguments(self.chains[name], "jvm"))
        before = regular_file_inventory(self.work)
        session = LookupSession(repository=producer["repository"], pull_request=31,
                                promoted_main=promoted, same_pr=same_pr, adapter_runtime_projection=callback)
        restored = session.lookup("same-pr", right_receipt)
        self.assertEqual(canonical_json_bytes(right_receipt), restored.envelope["receiptBytes"])
        self.assertEqual({"left", "right"}, set(calls))
        self.assertEqual(before, regular_file_inventory(self.work))
        for missing in (None, self.work / "missing-original.zip"):
            provider = Mock(wraps=callback)
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                LookupSession(repository=producer["repository"], pull_request=31,
                              promoted_main=replace(promoted, objects={left_receipt["buildKey"]: missing}),
                              same_pr=same_pr, adapter_runtime_projection=provider)
            provider.assert_not_called()

    def test_signed_writer_forwards_adapter_objects_and_provider_without_unneeded_verification(self):
        chain = self.chains["left"]
        _, receipt, raw = self.receipt(chain, "jvm")
        context = chain["context"]
        producer = context["producer"]
        provider = Mock()
        with patch.object(product_index, "build_product_index", wraps=build_product_index) as builder:
            write_signed_product_index(
                [IndexEntrySource(raw, receipt["outputs"][0]["relativePath"])],
                repository=producer["repository"],
                context={"kind": "pull-request", **{key: producer[key] for key in
                         ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
                trust_domain="development", signing=context["signing"], producer=producer,
                stable_history=None, private_key=context["private_key"], public_key=context["public_key"],
                manifest_path=self.work / "adapter-writer.json",
                adapter_runtime_objects={}, adapter_runtime_projection=provider,
            )
        self.assertEqual({}, builder.call_args.kwargs["adapter_runtime_objects"])
        self.assertIs(provider, builder.call_args.kwargs["adapter_runtime_projection"])
        provider.assert_not_called()

    def test_fresh_signed_changed_package_is_valid_but_remains_an_immutable_content_conflict(self):
        # The changed bytes were present before the original package receipts
        # and signatures were produced; no receipt is edited to force a key.
        for component in self.components:
            with self.subTest(component=component):
                originals = {name: self.signed_index_and_object(name, component) for name in ("left", "changed")}
                indexes = [originals[name][0] for name in ("left", "changed")]
                receipts = [originals[name][2] for name in ("left", "changed")]
                before = regular_file_inventory(self.work)
                proofs = {}
                for name, (index, archive, _) in originals.items():
                    entry = index["entries"][0]
                    def provider(actual_entry, actual_archive, original_name=name):
                        self.assertEqual(originals[original_name][0]["entries"][0], actual_entry)
                        self.assertEqual(originals[original_name][1], actual_archive)
                        return verify_runtime_adapter_projection(
                            component, self.target, **self.arguments(self.chains[original_name], component))
                    proofs[entry["receiptSha256"]] = verify_adapter_runtime_index_object(entry, archive, provider)
                entry_provider = lambda entry: proofs[entry["receiptSha256"]]
                views = [verified_index_content(index["entries"][0], adapter_runtime_projection=entry_provider)
                         for index in indexes]
                self.assertNotEqual(views[0]["outputs"], views[1]["outputs"])
                self.assertEqual(receipts[0]["productVersion"], receipts[1]["productVersion"])
                with self.assertRaises(ValueError):
                    verify_immutable_product_indexes(*indexes, adapter_runtime_projection=entry_provider)
                if receipts[0]["buildKey"] == receipts[1]["buildKey"]:
                    with self.assertRaises(ValueError):
                        verify_build_key_output_consistency(
                            receipts,
                            adapter_runtime_projection=lambda receipt: proofs[sha256_bytes(canonical_json_bytes(receipt))],
                        )
                self.assertEqual(before, regular_file_inventory(self.work))

    def test_all_adapter_families_authenticate_exact_originals_without_rewriting_bytes(self):
        chain = self.chains["left"]
        for component in self.components:
            with self.subTest(component=component):
                path, receipt, raw = self.receipt(chain, component)
                proof = verify_runtime_adapter_projection(component, self.target, **self.arguments(chain, component))
                inventory = self.inventory(proof, receipt, raw)
                self.assertEqual(1, len(inventory))
                self.assertEqual(raw, path.read_bytes())
                self.assertEqual(inventory, self.inventory(proof, receipt, raw))

    def test_distinct_signed_runs_with_unchanged_native_variants_have_equal_content(self):
        left, right = self.chains["left"], self.chains["right"]
        self.assertIs(left["variants"], right["variants"])
        self.assertNotEqual(left["context"]["signing"]["fingerprint"], right["context"]["signing"]["fingerprint"])
        for component in self.components:
            with self.subTest(component=component):
                inventories, receipts = [], []
                for chain in (left, right):
                    _, receipt, raw = self.receipt(chain, component)
                    proof = verify_runtime_adapter_projection(component, self.target, **self.arguments(chain, component))
                    inventories.append(self.inventory(proof, receipt, raw))
                    receipts.append(raw)
                self.assertNotEqual(receipts[0], receipts[1])
                self.assertEqual(inventories[0], inventories[1])

    def test_missing_raw_extra_stage_and_tampered_compiled_runner_fail(self):
        chain = self.chains["left"]
        for component in self.components:
            original = self.arguments(chain, component)
            for mutation in ("missing-raw", "extra-validation", "runner"):
                arguments = dict(original)
                field = "adapter_package_stage" if mutation == "runner" else "validation_stage"
                stage = self.work / component / mutation
                snapshot_regular_tree(arguments[field], stage)
                arguments[field] = stage
                if mutation == "missing-raw":
                    captures = list(stage.rglob("*-execution.json"))
                    self.assertEqual(1, len(captures))
                    captures[0].unlink()
                elif mutation == "extra-validation":
                    (stage / "outputs/undeclared-evidence.txt").write_bytes(b"not an original output")
                else:
                    runners = list((stage / "outputs/validation-runner").iterdir())
                    self.assertEqual(1, len(runners))
                    runners[0].write_bytes(runners[0].read_bytes() + b"different compiled runner")
                with self.subTest(component=component, mutation=mutation), self.assertRaises(ValueError):
                    verify_runtime_adapter_projection(component, self.target, **arguments)

    def test_cross_paired_host_and_adapter_package_stages_fail(self):
        chain = self.chains["left"]
        for component in self.components:
            original = self.arguments(chain, component)
            wrong_component = "node-js" if component == "jvm" else "jvm"
            replacements = {
                "validation_stage": chain["adapters"]["phase_stages"][
                    PhaseInstanceId("runtime", component, "validation", "macos-arm64")],
                "native_package_stage": chain["variants"]["stages"] / "macos-arm64/package",
                "adapter_package_stage": chain["adapters"]["phase_stages"][
                    PhaseInstanceId("runtime", wrong_component, "package", wrong_component)],
            }
            for field, path in replacements.items():
                with self.subTest(component=component, field=field), self.assertRaises(ValueError):
                    verify_runtime_adapter_projection(component, self.target, **{**original, field: path})

    def test_signature_tamper_and_forged_original_validation_receipt_fail(self):
        chain = self.chains["left"]
        arguments = self.arguments(chain, "jvm")
        signature = arguments["aggregate_inputs"]["aggregate_attestation_signature"]
        receipt_path, receipt, raw_receipt = self.receipt(chain, "jvm")
        forged = copy.deepcopy(receipt)
        forged["producer"]["runId"] += 1
        for path, changed in ((signature, b"invalid detached signature\n"),
                              (receipt_path, canonical_json_bytes(forged))):
            original = path.read_bytes()
            try:
                path.write_bytes(changed)
                with self.subTest(path=path.name), self.assertRaises(ValueError):
                    verify_runtime_adapter_projection("jvm", self.target, **arguments)
            finally:
                path.write_bytes(original)
        self.assertEqual(raw_receipt, receipt_path.read_bytes())

    def test_projection_rejects_other_original_receipt_outputs_and_every_identity_field(self):
        chain = self.chains["left"]
        _, receipt, raw = self.receipt(chain, "jvm")
        proof = verify_runtime_adapter_projection("jvm", self.target, **self.arguments(chain, "jvm"))
        _, _, other_raw = self.receipt(self.chains["right"], "jvm")
        with self.assertRaises(ValueError):
            proof.output_inventory(sha256_bytes(other_raw), receipt["outputs"], identity=self.identity(receipt))
        changed_outputs = copy.deepcopy(receipt["outputs"])
        changed_outputs[0]["sha256"] = sha256_bytes(b"not the original output")
        with self.assertRaises(ValueError):
            proof.output_inventory(sha256_bytes(raw), changed_outputs, identity=self.identity(receipt))
        for field in self.identity(receipt):
            changed = {**self.identity(receipt), field: "different"}
            with self.subTest(field=field), self.assertRaises(ValueError):
                proof.output_inventory(sha256_bytes(raw), receipt["outputs"], identity=changed)


if __name__ == "__main__":
    unittest.main()
