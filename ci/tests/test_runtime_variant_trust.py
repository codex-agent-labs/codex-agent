"""Real synthetic release signatures, not hosted/source or aggregate admission."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_release as fixture
from products import runtime_variant_trust as translator
from products.inventory import canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from products.registry import NATIVE_TARGETS
from products.signatures import generate_development_key


class RuntimeVariantTrustTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.RuntimeAggregateReleaseTest.setUpClass()
        cls.addClassCleanup(fixture.RuntimeAggregateReleaseTest.doClassCleanups)
        cls.source = fixture.RuntimeAggregateReleaseTest
        cls.handoffs = cls.source.handoffs
        cls.keyring, cls.keys = cls.source.keyring, cls.source.keys

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="variant-trust-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.output = self.work / "trust"

    def stage(self, handoffs=None, **changes):
        return translator.stage_runtime_variant_trust(self.handoffs if handoffs is None else handoffs,
            self.output, **{"keyring": self.keyring, "keys_directory": self.keys, **changes})

    def copies(self):
        result = {}
        for target, source in self.handoffs.items():
            result[target] = self.work / "originals" / target
            snapshot_regular_tree(source, result[target])
        return result

    def expected(self, handoffs):
        result = {}
        for target, source in handoffs.items():
            stem = self.source.chain["variants"]["variant_bundles"][target].stem
            for name in (f"{stem}.attestation.json", f"{stem}.attestation.sig", "public-key.pub"):
                result[f"{target}/{name}"] = (source / name).read_bytes()
        return result

    def test_exact_five_original_signatures_are_verified_and_forwarded_without_signing(self):
        before = {target: regular_file_inventory(path) for target, path in self.handoffs.items()}
        policy_before = self.keyring.read_bytes(), regular_file_inventory(self.keys)
        expected = self.expected(self.handoffs)
        with patch("products.runtime_attestation.sign_manifest", side_effect=AssertionError("translator signed")), \
                patch.object(translator, "read_runtime_variant_handoff",
                             wraps=translator.read_runtime_variant_handoff) as verify:
            self.assertEqual(self.output, self.stage())
        self.assertEqual(list(NATIVE_TARGETS), [call.kwargs["target"] for call in verify.call_args_list])
        inventory = regular_file_inventory(self.output)
        self.assertEqual(15, len(inventory))
        self.assertEqual(set(expected), {record["relativePath"] for record in inventory})
        for name, raw in expected.items():
            self.assertEqual(raw, (self.output / name).read_bytes())
        self.assertEqual(before, {target: regular_file_inventory(path) for target, path in self.handoffs.items()})
        self.assertEqual(policy_before, (self.keyring.read_bytes(), regular_file_inventory(self.keys)))

    def test_relocated_complete_handoffs_and_retired_caller_key_are_supported(self):
        originals = self.copies()
        policy = self.work / "policy"
        snapshot_regular_tree(self.keys, policy / "keys")
        keyring = policy / "product-signing-keys.json"
        keyring.write_bytes(canonical_json_bytes({**self.source.policy, "activeKey": None,
                                                 "retiredKeys": [self.source.policy["activeKey"]]}))
        self.stage(originals, keyring=keyring, keys_directory=policy / "keys")
        for name, raw in self.expected(originals).items():
            self.assertEqual(raw, (self.output / name).read_bytes())

    def test_exact_target_set_and_crosspaired_originals_are_required(self):
        targets = list(NATIVE_TARGETS)
        for handoffs in ({key: value for key, value in self.handoffs.items() if key != targets[0]},
                         {**self.handoffs, "unexpected": self.handoffs[targets[0]]},
                         {**self.handoffs, targets[-1]: self.handoffs[targets[0]]}):
            with self.subTest(targets=list(handoffs)), self.assertRaises(ValueError):
                self.stage(handoffs)
            self.assertFalse(self.output.exists())

    def test_missing_extra_symbolic_and_tampered_last_handoff_never_publish_partial_output(self):
        originals = self.copies()
        target = list(NATIVE_TARGETS)[-1]
        source = originals[target]
        stem = self.source.chain["variants"]["variant_bundles"][target].stem
        signature = source / f"{stem}.attestation.sig"
        raw = signature.read_bytes()
        signature.write_bytes(b"invalid SSH signature\n")
        try:
            with self.assertRaises(ValueError):
                self.stage(originals)
            self.assertFalse(self.output.exists())
        finally:
            signature.write_bytes(raw)
        signature.unlink()
        try:
            with self.assertRaises(ValueError):
                self.stage(originals)
            self.assertFalse(self.output.exists())
        finally:
            signature.write_bytes(raw)
        extra = source / "extra"
        extra.write_bytes(b"not an original\n")
        try:
            with self.assertRaises(ValueError):
                self.stage(originals)
            self.assertFalse(self.output.exists())
        finally:
            extra.unlink()
        signature.unlink()
        signature.symlink_to(self.handoffs[target] / signature.name)
        with self.assertRaises(ValueError):
            self.stage(originals)
        self.assertFalse(self.output.exists())

    def test_transported_public_keys_do_not_replace_caller_policy(self):
        _, public, signing = generate_development_key(self.work / "unrelated")
        keys = self.work / "wrong-policy/keys"
        keys.mkdir(parents=True)
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        keyring = keys.parent / "product-signing-keys.json"
        keyring.write_bytes(canonical_json_bytes({**self.source.policy,
            "activeKey": {name: signing[name] for name in ("keyId", "fingerprint")}}))
        for options in ({"keyring": None}, {"keys_directory": None}, {"keyring": keyring, "keys_directory": keys}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.stage(**options)
            self.assertFalse(self.output.exists())

    def test_original_or_private_policy_mutation_after_real_verification_prevents_publication(self):
        originals = self.copies()
        verify = translator.read_runtime_variant_handoff
        source = originals[list(NATIVE_TARGETS)[-1]] / "public-key.pub"
        raw = source.read_bytes()
        policy = self.work / "caller-policy"
        snapshot_regular_tree(self.keys, policy / "keys")
        keyring = policy / "product-signing-keys.json"
        policy_raw = self.keyring.read_bytes()
        keyring.write_bytes(policy_raw)
        for mutation in ("original", "private-policy", "caller-policy"):
            def mutate(*args, **kwargs):
                result = verify(*args, **kwargs)
                if kwargs["target"] == list(NATIVE_TARGETS)[-1]:
                    path = {"original": source, "private-policy": kwargs["keyring"], "caller-policy": keyring}[mutation]
                    path.write_bytes(path.read_bytes() + b"\n")
                return result
            try:
                with self.subTest(mutation=mutation), \
                        patch.object(translator, "read_runtime_variant_handoff", side_effect=mutate), \
                        self.assertRaises(ValueError):
                    self.stage(originals, keyring=keyring, keys_directory=policy / "keys")
                self.assertFalse(self.output.exists())
            finally:
                source.write_bytes(raw)
                keyring.write_bytes(policy_raw)

    def test_output_overlap_collision_and_symbolic_ancestry_preserve_originals(self):
        originals = self.copies()
        source = originals[list(NATIVE_TARGETS)[0]]
        before = regular_file_inventory(source)
        with self.assertRaises(ValueError):
            translator.stage_runtime_variant_trust(originals, source / "nested", keyring=self.keyring,
                                                   keys_directory=self.keys)
        self.output.mkdir()
        sentinel = self.output / "sentinel"
        sentinel.write_bytes(b"keep\n")
        with self.assertRaises(ValueError):
            self.stage(originals)
        self.assertEqual(b"keep\n", sentinel.read_bytes())
        alias = self.work / "alias"
        alias.symlink_to(source, target_is_directory=True)
        with self.assertRaises(ValueError):
            translator.stage_runtime_variant_trust(originals, alias / "nested", keyring=self.keyring,
                                                   keys_directory=self.keys)
        self.assertFalse((source / "nested").exists())
        self.assertEqual(before, regular_file_inventory(source))


if __name__ == "__main__":
    unittest.main()
