"""Original aggregate receipt release reuse over signed synthetic K/R inputs.

These tests exercise real signatures and complete existing admission, not hosted
execution, protected signing, or public-release acceptance.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import ci.products.reuse as reuse_module
from ci.products.contract_attestation import build_contract_attestation
from ci.products.index import (
    IndexEntrySource, release_attested_runtime_aggregate_admission, write_signed_product_index,
)
from ci.products.inventory import load_canonical_json_bytes, sha256_file, write_canonical_json
from ci.products.restore import store_local_object
from ci.products.reuse import LookupSession, RemoteCatalog, ReuseLookupError
from ci.products.runtime_aggregate import build_runtime_aggregate_attestation, validate_runtime_aggregate_attestation
from ci.products.runtime_attestation import build_runtime_variant_attestation
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.test_product_native_chain import build_chain


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class AggregateReleaseReuseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="aggregate-release-reuse-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chain = chain = build_chain(cls.root / "original", 691)
        context, contract, variants, adapters = (chain[name] for name in ("context", "contract", "variants", "adapters"))
        cls.repository = context["producer"]["repository"]
        signing = {**context["signing"], "trustDomain": "release", "keyId": "aggregate-test-key"}
        cls.keys = cls.root / "caller-keys"
        cls.keys.mkdir()
        (cls.keys / "aggregate-test-key.pub").write_bytes(context["public_key"].read_bytes())
        cls.keyring = cls.root / "caller-keyring.json"
        write_canonical_json(cls.keyring, {
            "schemaVersion": 1, "namespace": signing["namespace"], "algorithm": signing["algorithm"],
            "trustDomain": "release", "activeKey": {"keyId": signing["keyId"], "fingerprint": signing["fingerprint"]},
            "retiredKeys": [],
        })
        # New external release attestations authenticate the exact old payloads
        # and development receipts; no payload or original receipt is rewritten.
        contract_trust = cls.root / "release-contract"
        build_contract_attestation(
            contract["payload"], contract["receipt"], signing, context["private_key"], context["public_key"],
            contract_trust, execution_closure=contract["execution_closure"], keyring=cls.keyring, keys_directory=cls.keys)
        variant_inputs = {name: copy.deepcopy(variants[name]) for name in (
            "variant_bundles", "variant_phase_receipts", "variant_public_keys", "variant_validation_evidence")}
        variant_inputs.update(variant_attestations={}, variant_attestation_signatures={})
        for target, bundle in variants["variant_bundles"].items():
            receipts = variants["variant_phase_receipts"][target]
            output = cls.root / "release-variants" / target
            build_runtime_variant_attestation(
                bundle, *(receipts[phase] for phase in ("binary", "package", "validation", "metadata")),
                variants["variant_validation_evidence"][target], signing, context["private_key"],
                context["public_key"], output, keyring=cls.keyring, keys_directory=cls.keys)
            variant_inputs["variant_attestations"][target] = output / f"{bundle.stem}.attestation.json"
            variant_inputs["variant_attestation_signatures"][target] = output / f"{bundle.stem}.attestation.sig"
        cls.variant_inputs = variant_inputs
        aggregate_trust = cls.root / "release-aggregate"
        build_runtime_aggregate_attestation(
            chain["aggregate"], chain["aggregate_receipt"], **variant_inputs,
            adapter_receipts=adapters["adapter_receipts"], signing_metadata=signing,
            private_key=context["private_key"], public_key=context["public_key"], output_directory=aggregate_trust,
            required_variant_trust_domain="release", keyring=cls.keyring, keys_directory=cls.keys,
            variant_keyring=cls.keyring, variant_keys_directory=cls.keys,
            contract_payload=contract["payload"], contract_metadata_receipt=contract["receipt"],
            contract_attestation=contract_trust / "codex-agent-contract-0.2.0.attestation.json",
            contract_attestation_signature=contract_trust / "codex-agent-contract-0.2.0.attestation.sig",
            contract_public_key=context["public_key"], contract_keyring=cls.keyring, contract_keys_directory=cls.keys,
            adapter_report_files=adapters["adapter_report_files"], runtime_maven_files=adapters["runtime_maven_files"],
            adapter_evidence=adapters["adapter_evidence"],
        )
        cls.inputs = {
            **variant_inputs, "aggregate_metadata_receipt": chain["aggregate_receipt"],
            "aggregate_attestation": aggregate_trust / "codex-agent-runtime-0.2.7.attestation.json",
            "aggregate_attestation_signature": aggregate_trust / "codex-agent-runtime-0.2.7.attestation.sig",
            "aggregate_public_key": context["public_key"], "adapter_receipts": adapters["adapter_receipts"],
            # Transported paths cannot become the release authority.
            "aggregate_keyring": cls.root / "not-authority", "variant_keyring": cls.root / "not-authority",
        }
        cls.raw = chain["aggregate_receipt"].read_bytes()
        cls.receipt = load_canonical_json_bytes(cls.raw)
        cls.evidence = {"original-adapter-host": {
            "aggregate_manifest": chain["aggregate"], "aggregate_inputs": cls.inputs,
        }}
        stage = cls.root / "aggregate-stage"
        for output in cls.receipt["outputs"]:
            path = stage / output["relativePath"]
            path.parent.mkdir(parents=True)
            path.write_bytes(chain["aggregate"].read_bytes())
        write_canonical_json(stage / "output-manifest.json", {
            "schemaVersion": 1, **{key: cls.receipt[key] for key in
                ("product", "component", "phase", "target", "productVersion")}, "outputs": cls.receipt["outputs"],
        })
        cls.object = store_local_object(stage, chain["aggregate_receipt"], cls.root / "objects")["path"]
        source = IndexEntrySource(cls.raw, cls.receipt["outputs"][0]["relativePath"])
        admission = release_attested_runtime_aggregate_admission(
            source, manifest=chain["aggregate"], metadata_receipt=chain["aggregate_receipt"],
            attestation=cls.inputs["aggregate_attestation"], signature=cls.inputs["aggregate_attestation_signature"],
            public_key=context["public_key"], **variant_inputs, adapter_receipts=adapters["adapter_receipts"],
            keyring=cls.keyring, keys_directory=cls.keys, variant_keyring=cls.keyring, variant_keys_directory=cls.keys)
        cls.manifest = cls.root / "product-index.json"
        write_signed_product_index(
            [IndexEntrySource(cls.raw, source.artifact_path, admission)], repository=cls.repository,
            context={"kind": "promoted-main", "commit": "c" * 40, "tree": "d" * 40,
                     "promotionRunId": 791, "promotionRunAttempt": 1},
            trust_domain="release", signing=signing,
            producer={**context["producer"], "event": "push", "pullRequest": None,
                      "commit": "c" * 40, "tree": "d" * 40, "runId": 791},
            stable_history=None, private_key=context["private_key"], public_key=context["public_key"],
            manifest_path=cls.manifest)
        cls.catalog = RemoteCatalog(
            cls.manifest, cls.manifest.with_suffix(".sig"), {cls.receipt["buildKey"]: cls.object},
            keyring=cls.keyring, keys_directory=cls.keys)

    def session(self, evidence=None, catalog=None):
        return LookupSession(repository=self.repository, pull_request=31,
                             promoted_main=self.catalog if catalog is None else catalog,
                             adapter_runtime_evidence=self.evidence if evidence is None else evidence)

    def test_release_lookup_authenticates_exact_original_aggregate_without_receipt_rewrite(self):
        originals = {path: path.read_bytes() for path in (
            self.chain["aggregate"], self.chain["aggregate_receipt"], self.inputs["aggregate_attestation"],
            self.inputs["aggregate_attestation_signature"], self.object)}
        result = self.session().lookup("promoted-main", self.receipt)
        self.assertIsNone(result.reason)
        self.assertEqual(self.raw, result.envelope["receiptBytes"])
        self.assertEqual("development", result.envelope["receipt"]["trustDomain"])
        self.assertEqual(self.receipt["producer"], result.envelope["receipt"]["producer"])
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})

    def test_missing_crosspaired_and_development_only_attestation_reject(self):
        with self.assertRaises(ReuseLookupError):
            self.session({}).lookup("promoted-main", self.receipt)
        for changed in (
            {"aggregate_metadata_receipt": self.chain["contract"]["receipt"]},
            {"aggregate_attestation": self.chain["root"] / "aggregate-trust/codex-agent-runtime-0.2.7.attestation.json",
             "aggregate_attestation_signature": self.chain["root"] / "aggregate-trust/codex-agent-runtime-0.2.7.attestation.sig"},
            {"variant_attestations": self.chain["variants"]["variant_attestations"],
             "variant_attestation_signatures": self.chain["variants"]["variant_attestation_signatures"]},
        ):
            evidence = {"original": {"aggregate_manifest": self.chain["aggregate"],
                                     "aggregate_inputs": {**self.inputs, **changed}}}
            with self.subTest(changed=tuple(changed)), self.assertRaises(ReuseLookupError):
                self.session(evidence).lookup("promoted-main", self.receipt)
        with self.assertRaises(ValueError):
            self.session(catalog=replace(self.catalog, keyring=None))

    def test_changed_original_variant_receipt_rejects_complete_closure(self):
        target = next(iter(self.variant_inputs["variant_phase_receipts"]))
        path = self.variant_inputs["variant_phase_receipts"][target]["binary"]
        original = path.read_bytes()
        try:
            value = load_canonical_json_bytes(original)
            write_canonical_json(path, {**value, "producer": {**value["producer"], "runId": 999}})
            with self.assertRaises(ReuseLookupError):
                self.session().lookup("promoted-main", self.receipt)
        finally:
            path.write_bytes(original)

    def test_policy_swap_cannot_separate_aggregate_trust_from_original_index_trust(self):
        with tempfile.TemporaryDirectory(prefix="aggregate-unrelated-policy-") as temporary:
            root = Path(temporary).resolve()
            private, public, development = generate_development_key(root / "key")
            signing = {**development, "trustDomain": "release", "keyId": "aggregate-test-key"}
            keys = root / "public-keys"
            keys.mkdir()
            (keys / "aggregate-test-key.pub").write_bytes(public.read_bytes())
            keyring = root / "keyring.json"
            policy = {"schemaVersion": 1, "namespace": signing["namespace"], "algorithm": signing["algorithm"],
                      "trustDomain": "release", "activeKey": {"keyId": signing["keyId"],
                      "fingerprint": signing["fingerprint"]}, "retiredKeys": []}
            write_canonical_json(keyring, policy)
            variants = {**self.variant_inputs, "variant_attestations": {}, "variant_attestation_signatures": {},
                        "variant_public_keys": {target: public for target in self.variant_inputs["variant_bundles"]}}
            for target, bundle in variants["variant_bundles"].items():
                receipts = variants["variant_phase_receipts"][target]
                output = root / "variants" / target
                build_runtime_variant_attestation(
                    bundle, *(receipts[phase] for phase in ("binary", "package", "validation", "metadata")),
                    variants["variant_validation_evidence"][target], signing, private, public, output,
                    keyring=keyring, keys_directory=keys)
                variants["variant_attestations"][target] = output / f"{bundle.stem}.attestation.json"
                variants["variant_attestation_signatures"][target] = output / f"{bundle.stem}.attestation.sig"
            # Independently valid external B signatures over the SAME original
            # payload/receipts; the existing full admission verifies them below.
            value = load_canonical_json_bytes(self.inputs["aggregate_attestation"].read_bytes())
            value = validate_runtime_aggregate_attestation({**value, "signing": signing,
                "variants": [{**record, "variantAttestationSha256":
                              sha256_file(variants["variant_attestations"][record["target"]])}
                             for record in value["variants"]]})
            attestation = root / self.inputs["aggregate_attestation"].name
            write_canonical_json(attestation, value)
            signature = sign_manifest(attestation, private, signing)
            release_attested_runtime_aggregate_admission(
                IndexEntrySource(self.raw, self.receipt["outputs"][0]["relativePath"]),
                manifest=self.chain["aggregate"], metadata_receipt=self.chain["aggregate_receipt"],
                attestation=attestation, signature=signature, public_key=public, **variants,
                adapter_receipts=self.inputs["adapter_receipts"], keyring=keyring, keys_directory=keys,
                variant_keyring=keyring, variant_keys_directory=keys)
            evidence = {"original": {"aggregate_manifest": self.chain["aggregate"], "aggregate_inputs": {
                **self.inputs, **variants, "aggregate_attestation": attestation,
                "aggregate_attestation_signature": signature, "aggregate_public_key": public}}}
            session = self.session(evidence)  # The original signed catalog is verified under A.
            caller_public = self.keys / "aggregate-test-key.pub"
            original_policy, original_public = self.keyring.read_bytes(), caller_public.read_bytes()
            try:
                self.keyring.write_bytes(keyring.read_bytes())
                caller_public.write_bytes(public.read_bytes())
                with self.assertRaises(ReuseLookupError):
                    session.lookup("promoted-main", self.receipt)
            finally:
                self.keyring.write_bytes(original_policy)
                caller_public.write_bytes(original_public)

    def test_full_verifier_receives_private_exact_original_captures(self):
        target = next(iter(self.variant_inputs["variant_phase_receipts"]))
        original_path = self.variant_inputs["variant_phase_receipts"][target]["binary"]
        original = original_path.read_bytes()

        def verify(source, **arguments):
            captured = arguments["variant_phase_receipts"][target]["binary"]
            self.assertNotEqual(original_path, captured)
            self.assertEqual(original, captured.read_bytes())
            self.assertEqual(self.raw, arguments["metadata_receipt"].read_bytes())
            self.assertNotEqual(self.keyring, arguments["keyring"])
            try:
                original_path.write_bytes(b"concurrent external change\n")
                return release_attested_runtime_aggregate_admission(source, **arguments)
            finally:
                original_path.write_bytes(original)

        with patch.object(reuse_module, "release_attested_runtime_aggregate_admission", side_effect=verify) as gate:
            result = self.session().lookup("promoted-main", self.receipt)
        self.assertEqual(self.raw, result.envelope["receiptBytes"])
        gate.assert_called_once()
