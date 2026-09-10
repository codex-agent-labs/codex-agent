"""Complete signed synthetic carrier transport; no hosted or source authority."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_handoff as fixture
from products import runtime_aggregate_inputs as transport
from products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_file, snapshot_regular_tree,
)
from products.signatures import generate_development_key


class RuntimeAggregateInputsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = fixture.RuntimeAggregateHandoffTest
        source.setUpClass()
        cls.addClassCleanup(source.doClassCleanups)
        cls.source = source
        cls.carrier, cls.keyring, cls.keys = source.carrier, source.keyring, source.keys
        cls.digest = sha256_file(cls.carrier / "aggregate-input/metadata-receipt.json")
        cls.records = [{"receiptSha256": cls.digest, "handoffRoot": cls.carrier.name}]

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aggregate-inputs-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.output = self.work / "transport"

    def stage(self, records=None, source_root=None, **changes):
        return transport.stage_runtime_aggregate_release_evidence(
            self.records if records is None else records,
            self.carrier.parent if source_root is None else source_root, self.output,
            **{"keyring": self.keyring, "keys_directory": self.keys, **changes})

    def copy(self):
        source = self.work / "originals" / self.carrier.name
        snapshot_regular_tree(self.carrier, source, allow_empty=True)
        return source

    def test_full_verified_original_carrier_survives_relocation_without_signing(self):
        before = regular_file_inventory(self.carrier, allow_empty=True)
        policy_before = self.keyring.read_bytes(), regular_file_inventory(self.keys)
        with patch("products.runtime_aggregate.sign_manifest", side_effect=AssertionError("transport signed")), \
                patch("reuse.api_request", side_effect=AssertionError("transport contacted CI")), \
                patch.object(transport, "verified_runtime_aggregate_handoff",
                             wraps=transport.verified_runtime_aggregate_handoff) as verify:
            records = self.stage()
        verify.assert_called_once()
        expected = [{"receiptSha256": self.digest, "handoffRoot": f"handoffs/{self.digest[7:]}"}]
        self.assertEqual(expected, records)
        self.assertEqual(expected, transport.load_runtime_aggregate_release_evidence(self.output))
        self.assertEqual(before, regular_file_inventory(self.output / expected[0]["handoffRoot"], allow_empty=True))
        self.assertEqual(before, regular_file_inventory(self.carrier, allow_empty=True))
        self.assertEqual(policy_before, (self.keyring.read_bytes(), regular_file_inventory(self.keys)))

        relocated = self.work / "relocated"
        snapshot_regular_tree(self.output, relocated, allow_empty=True)
        rebased = transport.rebase_runtime_aggregate_release_records(records, relocated, self.work)
        self.assertEqual(f"relocated/handoffs/{self.digest[7:]}", rebased[0]["handoffRoot"])
        self.assertEqual(records, transport.load_runtime_aggregate_release_evidence(relocated))
        # Only the relocated direct carrier is passed to the same real reader;
        # the original is absent, so no original absolute path can be needed.
        hidden = self.carrier.with_name("hidden-original")
        self.carrier.rename(hidden)
        try:
            with transport.verified_runtime_aggregate_handoff(
                    self.work / rebased[0]["handoffRoot"], keyring=self.keyring, keys_directory=self.keys) as verified:
                self.assertEqual(before, verified["inventory"])
                self.assertEqual(self.digest, sha256_file(verified["directory"] / "aggregate-input/metadata-receipt.json"))
        finally:
            hidden.rename(self.carrier)

    def test_descriptor_requires_sorted_unique_nonoverlapping_relative_roots(self):
        first = {"receiptSha256": "sha256:" + "1" * 64, "handoffRoot": "one"}
        second = {"receiptSha256": "sha256:" + "2" * 64, "handoffRoot": "two"}
        cases = ([second, first], [first, first], [{**first, "extra": True}],
                 [first, {**second, "handoffRoot": "one/child"}],
                 [{**first, "receiptSha256": "not-a-digest"}])
        cases += tuple([{**first, "handoffRoot": path}] for path in
                       ("../escape", "/absolute", "a/../b", "a//b", "a\\b", ".", transport.REQUEST_NAME))
        for records in cases:
            with self.subTest(records=records), \
                    patch.object(transport, "verified_runtime_aggregate_handoff") as verify, self.assertRaises(ValueError):
                self.stage(records)
            verify.assert_not_called()
            self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):
            transport.rebase_runtime_aggregate_release_records([first], self.work, self.work / "elsewhere")

    def test_loader_enforces_outer_inventory_and_containment_without_granting_trust(self):
        root = self.work / "structural-only"
        declared = root / "handoffs/one"
        declared.mkdir(parents=True)
        (declared / "unverified-data").write_bytes(b"this is not a signed carrier\n")
        (declared / "empty-diagnostic.log").write_bytes(b"")
        records = [{"receiptSha256": self.digest, "handoffRoot": "handoffs/one"}]
        descriptor = root / transport.REQUEST_NAME
        descriptor.write_bytes(canonical_json_bytes(records))
        with patch.object(transport, "verified_runtime_aggregate_handoff", side_effect=AssertionError("loader granted trust")):
            self.assertEqual(records, transport.load_runtime_aggregate_release_evidence(root))
        with self.assertRaises(ValueError):
            self.stage(records, root)
        self.assertFalse(self.output.exists())
        extra = root / "extra"
        extra.write_bytes(b"undeclared\n")
        with self.assertRaises(ValueError):
            transport.load_runtime_aggregate_release_evidence(root)
        extra.unlink()
        descriptor.write_bytes(canonical_json_bytes([{**records[0], "handoffRoot": "missing"}]))
        with self.assertRaises(ValueError):
            transport.load_runtime_aggregate_release_evidence(root)
        link = root / "linked"
        link.symlink_to(declared, target_is_directory=True)
        descriptor.write_bytes(canonical_json_bytes([{**records[0], "handoffRoot": "linked"}]))
        with self.assertRaises(ValueError):
            transport.load_runtime_aggregate_release_evidence(root)

    def test_tampered_or_crosspaired_complete_carrier_never_publishes(self):
        source = self.copy()
        signature = source / "aggregate-input/codex-agent-runtime-0.2.7.attestation.sig"
        raw = signature.read_bytes()
        signature.write_bytes(b"invalid SSH signature\n")
        try:
            with self.assertRaises(ValueError):
                self.stage(source_root=source.parent)
            self.assertFalse(self.output.exists())
        finally:
            signature.write_bytes(raw)
        wrong = [{**self.records[0], "receiptSha256": "sha256:" + "0" * 64}]
        with self.assertRaisesRegex(ValueError, "original metadata receipt"):
            self.stage(wrong, source.parent)
        self.assertFalse(self.output.exists())
        # Preserve arbitrary empty external diagnostics, but never synthesize
        # an absent field in the existing exact complete carrier layout.
        extra = source / "unexpected"
        extra.write_bytes(b"extra\n")
        with self.assertRaises(ValueError):
            self.stage(source_root=source.parent)
        self.assertFalse(self.output.exists())

    def test_caller_pin_is_required_and_retired_signatures_remain_valid(self):
        _, public, signing = generate_development_key(self.work / "unrelated")
        keys = self.work / "wrong-policy/keys"
        keys.mkdir(parents=True)
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        keyring = keys.parent / "product-signing-keys.json"
        policy = self.source.source.policy
        keyring.write_bytes(canonical_json_bytes({**policy,
            "activeKey": {name: signing[name] for name in ("keyId", "fingerprint")}}))
        for options in ({"keyring": None}, {"keys_directory": None}, {"keyring": keyring, "keys_directory": keys}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.stage(**options)
            self.assertFalse(self.output.exists())
        retired = self.work / "retired-policy"
        snapshot_regular_tree(self.keys, retired / "keys")
        (retired / "product-signing-keys.json").write_bytes(canonical_json_bytes(
            {**policy, "activeKey": None, "retiredKeys": [policy["activeKey"]]}))
        self.stage(keyring=retired / "product-signing-keys.json", keys_directory=retired / "keys")
        self.assertEqual(regular_file_inventory(self.carrier, allow_empty=True),
                         regular_file_inventory(self.output / f"handoffs/{self.digest[7:]}", allow_empty=True))

    def test_late_original_mutation_and_hostile_outputs_preserve_inputs(self):
        source = self.copy()
        signature = source / "aggregate-input/codex-agent-runtime-0.2.7.attestation.sig"
        raw = signature.read_bytes()
        reader = transport.verified_runtime_aggregate_handoff

        @contextmanager
        def mutate(*args, **kwargs):
            with reader(*args, **kwargs) as verified:
                yield verified
            signature.write_bytes(raw + b"changed-after-reader-exit\n")

        try:
            with patch.object(transport, "verified_runtime_aggregate_handoff", side_effect=mutate), self.assertRaises(ValueError):
                self.stage(source_root=source.parent)
            self.assertFalse(self.output.exists())
        finally:
            signature.write_bytes(raw)
        before = regular_file_inventory(source, allow_empty=True)
        alias = self.work / "alias"
        alias.symlink_to(source, target_is_directory=True)
        for output in (source / "nested", alias / "nested", source):
            with self.subTest(output=output), self.assertRaises(ValueError):
                transport.stage_runtime_aggregate_release_evidence(self.records, source.parent, output,
                    keyring=self.keyring, keys_directory=self.keys)
        self.output.mkdir()
        (self.output / "sentinel").write_bytes(b"keep\n")
        with self.assertRaises(ValueError):
            self.stage(source_root=source.parent)
        self.assertEqual(b"keep\n", (self.output / "sentinel").read_bytes())
        self.assertEqual(before, regular_file_inventory(source, allow_empty=True))


class RuntimeAggregateInputsCliTest(unittest.TestCase):
    def test_cli_forwards_explicit_request_roots_and_required_caller_pin(self):
        with tempfile.TemporaryDirectory(prefix="aggregate-inputs-cli-") as temporary:
            root = Path(temporary).resolve()
            request = root / "request.json"
            records = [{"receiptSha256": "sha256:" + "a" * 64, "handoffRoot": "original"}]
            request.write_bytes(canonical_json_bytes(records))
            arguments = ["--request", str(request), "--source-root", str(root),
                         "--output", str(root / "output"), "--keyring", str(root / "pinned.json"),
                         "--keys-directory", str(root / "keys")]
            with patch.object(transport, "stage_runtime_aggregate_release_evidence") as stage:
                self.assertEqual(0, transport.main(arguments))
                stage.assert_called_once_with(records, root, root / "output",
                    keyring=root / "pinned.json", keys_directory=root / "keys")
            with patch.object(transport, "stage_runtime_aggregate_release_evidence") as stage, \
                    self.assertRaises(SystemExit) as error:
                transport.main(arguments[:-2])
            self.assertEqual(2, error.exception.code)
            stage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
