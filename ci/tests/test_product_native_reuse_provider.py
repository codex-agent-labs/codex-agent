"""Signed synthetic provider selection, not planner or hosted campaign acceptance."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products import reuse
from ci.products.inventory import load_canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.products.plan import native_runtime_validation_dependencies
from ci.products.registry import PhaseInstanceId
from ci.tests.test_product_native_chain import build_chain


class NativeReuseProviderTest(unittest.TestCase):
    instance = PhaseInstanceId("sdk", "python", "validation", "linux-x64")

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="native-provider-fixtures-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chains = {
            "selected": build_chain(cls.root / "selected", 201, include_bootstrap=True),
            "other": build_chain(cls.root / "other", 202),
        }

    def setUp(self):
        self.original = regular_file_inventory(self.root, allow_empty=True)
        self.addCleanup(lambda: self.assertEqual(self.original, regular_file_inventory(self.root, allow_empty=True)))

    def relative(self, path):
        return path.relative_to(self.root).as_posix()

    def envelope(self, path):
        raw = path.read_bytes()
        return {"receipt": load_canonical_json_bytes(raw), "receiptBytes": raw,
                "receiptSha256": sha256_bytes(raw)}

    def contract_evidence(self, chain):
        contract = chain["contract"]
        return {
            "attestation": self.relative(contract["attestation"]),
            "attestationSignature": self.relative(contract["signature"]),
            "publicKey": self.relative(chain["context"]["public_key"]),
            "expectedTrustDomain": "development", "keyring": None, "keysDirectory": None,
        }

    def runtime_evidence(self, chain, target):
        variants = chain["variants"]
        return {
            "target": target, "stageRoot": self.relative(variants["stages"]),
            "phaseReceipts": {phase: self.relative(path)
                              for phase, path in variants["variant_phase_receipts"][target].items()},
            **{field: self.relative(variants[key][target]) for field, key in (
                ("payload", "variant_bundles"), ("attestation", "variant_attestations"),
                ("attestationSignature", "variant_attestation_signatures"),
                ("publicKey", "variant_public_keys"))},
            "keyring": None, "keysDirectory": None,
        }

    def request(self):
        chain = self.chains["selected"]
        identities = reuse._dependency_closure((self.instance,))
        def identity(instance):
            return {key: getattr(instance, key) for key in ("product", "component", "phase", "target")}
        comparisons = []
        for dependency in native_runtime_validation_dependencies(self.instance):
            target = dependency.target
            envelope = self.envelope(chain["variants"]["variant_phase_receipts"][target]["validation"])
            comparisons.append({
                "receiptSha256": envelope["receiptSha256"],
                "contractEvidence": {
                    **self.contract_evidence(chain),
                    "stageRoot": self.relative(chain["contract"]["payload"].parent.parent),
                    "phaseReceipt": self.relative(chain["contract"]["receipt"]),
                },
                "runtimeEvidence": self.runtime_evidence(chain, target),
            })
        return {
            "schemaVersion": 1, "requestType": "reuse-wave", "repository": chain["context"]["producer"]["repository"],
            "pullRequest": 31, "repositoryRoot": str(self.root),
            "repositoryRevision": chain["context"]["producer"]["commit"], "artifactRoot": str(self.root),
            "requested": [identity(self.instance)],
            "versions": {"contract": "0.2.0", "runtime-compatibility": "0.2.0", "runtime-release": "0.2.7", "sdk": "0.2.0"},
            "phaseAuthorities": [{**identity(instance), "toolchainProfileDigest": sha256_bytes(b"fixture toolchain"),
                                  "flagsDigest": sha256_bytes(b"fixture flags"), "outputSchemaVersion": 1}
                                 for instance in identities],
            "contractEvidence": self.contract_evidence(chain), "runtimeValidationEvidence": [],
            "nativeRuntimeComparisonEvidence": sorted(comparisons, key=lambda item: item["receiptSha256"]),
            "availableObjects": [], "catalogs": {"stable": [], "promotedMain": None, "samePr": None, "local": None},
        }

    def invoke(self, request, check, *, other_selected=False):
        chain = self.chains["selected"]
        envelopes = tuple(self.envelope(
            self.chains["other" if other_selected and dependency.target == "linux-x64" else "selected"]
            ["variants"]["variant_phase_receipts"][dependency.target]["validation"])
            for dependency in native_runtime_validation_dependencies(self.instance))
        def advance(*_args, **kwargs):
            projection = kwargs["contract_projection_provider"](
                self.instance, self.envelope(chain["contract"]["receipt"]))
            proofs = kwargs["native_runtime_projection_provider"](self.instance, envelopes, projection)
            check(proofs, envelopes, projection)
            return {"providerOnly": True}, ()
        # Only inventory/discovery and the outer delegate are substituted. The
        # actual Contract and native K/R authentication/semantic gates run intact.
        with patch.object(reuse, "phase_git_inventory", return_value=[]), \
                patch.object(reuse.LookupSession, "contract_stage", return_value=chain["contract"]["payload"].parent.parent), \
                patch.object(reuse, "advance_reuse", side_effect=advance) as delegated:
            self.assertEqual({"providerOnly": True}, reuse.plan_reuse_wave(request))
        delegated.assert_called_once()

    def test_exact_selected_original_receipts_choose_full_signed_comparison_closure(self):
        def check(proofs, envelopes, projection):
            self.assertEqual([item["receipt"]["target"] for item in envelopes], [proof.target for proof in proofs])
            for proof, envelope in zip(proofs, envelopes, strict=True):
                self.assertEqual(envelope["receiptSha256"],
                                 proof.receipt_value(envelope["receipt"], projection)["receiptSha256"])
        self.invoke(self.request(), check)

    def test_same_target_different_original_receipt_is_not_a_comparison_match(self):
        self.invoke(self.request(), lambda proofs, *_: self.assertIsNone(proofs), other_selected=True)

    def test_absent_comparison_map_leaves_evidence_unavailable(self):
        request = self.request()
        request.pop("nativeRuntimeComparisonEvidence")
        self.invoke(request, lambda proofs, *_: self.assertIsNone(proofs))

    def test_explicit_other_original_does_not_silently_fall_back_to_matching_comparison(self):
        request = copy.deepcopy(self.request())
        request["nativeRuntimeEvidence"] = [self.runtime_evidence(self.chains["other"], "linux-x64")]
        with self.assertRaisesRegex(ValueError, "another original receipt"):
            self.invoke(request, lambda *_: self.fail("Wrong explicit evidence must not produce a proof"))


if __name__ == "__main__":
    unittest.main()
