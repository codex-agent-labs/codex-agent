"""Full signed synthetic aggregate carrier reads; never hosted/source execution."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_release as fixture
from products import runtime_aggregate_handoff as reader
from products.inventory import canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from products.signatures import generate_development_key


class RuntimeAggregateHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.RuntimeAggregateReleaseTest.setUpClass()
        cls.addClassCleanup(fixture.RuntimeAggregateReleaseTest.doClassCleanups)
        cls.source = fixture.RuntimeAggregateReleaseTest()
        cls.source.setUp()
        cls.addClassCleanup(cls.source.doCleanups)
        # The existing leaf fixture adds a deliberately external sentinel. The
        # real selector's fixed layout has no such file: use a new input capture
        # before the original caller runs; never alter finalized carrier bytes.
        selected = cls.source.work / "selected"
        snapshot_regular_tree(cls.source.selected, selected, allow_empty=True)
        (selected / "empty-diagnostic.log").unlink()
        with patch("reuse.api_request", side_effect=cls.source.api):
            cls.source.invoke(selected_root=selected)
        cls.carrier = cls.source.output
        cls.keyring, cls.keys = cls.source.keyring, cls.source.keys

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aggregate-handoff-read-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()

    def read(self, root=None, **changes):
        return reader.verified_runtime_aggregate_handoff(self.carrier if root is None else root,
            **{"keyring": self.keyring, "keys_directory": self.keys, **changes})

    def copy(self):
        root = self.work / "carrier"
        snapshot_regular_tree(self.carrier, root, allow_empty=True)
        return root

    def test_full_signed_reader_retains_fifty_originals_and_all_five_native_gates_without_signing(self):
        before = regular_file_inventory(self.carrier, allow_empty=True)
        with patch("reuse.api_request", side_effect=AssertionError("retained read contacted CI")), \
                patch("products.runtime_aggregate.sign_manifest", side_effect=AssertionError("retained read signed")), \
                patch.object(reader, "verify_native_runtime_validation_content",
                             wraps=reader.verify_native_runtime_validation_content) as native, \
                patch.object(reader, "verify_runtime_aggregate_artifacts",
                             wraps=reader.verify_runtime_aggregate_artifacts) as aggregate, self.read() as verified:
            self.assertEqual(50, len(verified["receiptBytes"]))
            self.assertEqual("0.2.7", verified["manifest"]["runtimeVersion"])
            self.assertEqual(list(NATIVE_TARGETS), [call.args[0] for call in native.call_args_list])
            aggregate.assert_called_once()
            self.assertNotEqual(self.carrier, verified["directory"])
            self.assertEqual(before, verified["inventory"])
            self.assertEqual(before, regular_file_inventory(verified["directory"], allow_empty=True))
            self.assertEqual(25, len(verified["attestation"]["adapterReceipts"]))
            instance = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
            self.assertEqual(self.source.chain["aggregate_receipt"].read_bytes(), verified["receiptBytes"][instance])
            private = verified["directory"]
        self.assertFalse(private.exists())
        self.assertEqual(before, regular_file_inventory(self.carrier, allow_empty=True))

    def test_relocated_original_and_retired_key_policy_need_no_active_key_or_original_paths(self):
        relocated = self.copy()
        policy = self.work / "retired-policy"
        snapshot_regular_tree(self.keys, policy / "keys")
        keyring = policy / "product-signing-keys.json"
        value = {**self.source.policy, "activeKey": None, "retiredKeys": [self.source.policy["activeKey"]]}
        keyring.write_bytes(canonical_json_bytes(value))
        hidden = self.carrier.with_name("temporarily-absent-original")
        self.carrier.rename(hidden)
        try:
            with patch("reuse.api_request", side_effect=AssertionError("retired read contacted CI")), \
                    self.read(relocated, keyring=keyring, keys_directory=policy / "keys") as verified:
                self.assertEqual("release", verified["attestation"]["signing"]["trustDomain"])
                self.assertEqual(50, len(verified["receipts"]))
        finally:
            hidden.rename(self.carrier)

    def test_transport_policy_is_never_a_substitute_for_the_caller_pin(self):
        _, public, signing = generate_development_key(self.work / "wrong-key")
        keys = self.work / "wrong-policy/keys"
        keys.mkdir(parents=True)
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        keyring = keys.parent / "product-signing-keys.json"
        keyring.write_bytes(canonical_json_bytes({**self.source.policy,
            "activeKey": {name: signing[name] for name in ("keyId", "fingerprint")}}))
        for options in ({"keyring": None}, {"keys_directory": None}, {"keyring": keyring, "keys_directory": keys}):
            with self.subTest(options=options), patch("reuse.api_request", side_effect=AssertionError("fallback HTTP")), \
                    self.assertRaises(ValueError), self.read(**options):
                self.fail("Unpinned release read accepted")

    def test_missing_extra_symbolic_and_recursive_wrapper_inputs_are_rejected(self):
        root = self.copy()
        for path in (root / "unexpected-file", root / "aggregate-input/unexpected-file",
                     root / "selected-inputs/unexpected-file"):
            path.write_bytes(b"not an original carrier file\n")
            try:
                with self.subTest(path=path), self.assertRaises(ValueError), self.read(root):
                    self.fail("Extra carrier file accepted")
            finally:
                path.unlink()
        signature = next((root / "aggregate-input").glob("*.attestation.sig"))
        raw = signature.read_bytes()
        signature.unlink()
        try:
            with self.assertRaises((ValueError, OSError)), self.read(root):
                self.fail("Missing signature accepted")
        finally:
            signature.write_bytes(raw)
        alias = root / "external-link"
        alias.symlink_to(self.keyring)
        with self.assertRaises(ValueError), self.read(root):
            self.fail("Symbolic carrier accepted")
        wrapper = self.work / "wrapper"
        wrapper.mkdir()
        snapshot_regular_tree(self.carrier, wrapper / "retained-release", allow_empty=True)
        with self.assertRaisesRegex(ValueError, "direct original carrier"), self.read(wrapper):
            self.fail("Recursive wrapper accepted")

    def test_raw_native_adapter_and_original_upload_bytes_are_all_bound(self):
        root = self.copy()
        paths = [
            root / "runtime-stages/linux-x64/validation/outputs/c-abi-reference/include/codex_agent.h",
            next((root / "selected-inputs/predecessors/runtime-jvm-validation-linux-x64/stage/outputs/jvm-evidence").glob("*.json")),
            root / "original-evidence/phases/runtime-aggregate-metadata-aggregate/transport.zip",
            root / "original-evidence/phases/runtime-aggregate-metadata-aggregate/original/empty-diagnostic.log",
        ]
        for path in paths:
            raw, mode = path.read_bytes(), path.stat().st_mode
            try:
                path.chmod(0o600)
                path.write_bytes(raw + b"altered original\n")
                with self.subTest(path=path), self.assertRaises((ValueError, OSError)), self.read(root):
                    self.fail("Changed original evidence accepted")
            finally:
                path.write_bytes(raw)
                path.chmod(mode)

    def test_context_rechecks_original_private_capture_and_caller_policy_before_reuse(self):
        root = self.copy()
        path = root / "caller.json"
        raw, mode = path.read_bytes(), path.stat().st_mode
        try:
            with self.assertRaisesRegex(ValueError, "changed during verification"):
                with self.read(root):
                    path.chmod(0o600)
                    path.write_bytes(raw + b"changed external provenance\n")
        finally:
            path.write_bytes(raw)
            path.chmod(mode)
        with self.assertRaisesRegex(ValueError, "changed during verification"):
            with self.read(root) as verified:
                private = verified["directory"] / "caller.json"
                private.write_bytes(private.read_bytes() + b"changed private capture\n")
        policy = self.work / "policy"
        snapshot_regular_tree(self.keys, policy / "keys")
        keyring = policy / "product-signing-keys.json"
        keyring.write_bytes(self.keyring.read_bytes())
        with self.assertRaisesRegex(ValueError, "changed during verification"):
            with self.read(root, keyring=keyring, keys_directory=policy / "keys"):
                keyring.write_bytes(keyring.read_bytes() + b"\n")

    def test_optional_current_state_capture_is_preserved_but_never_an_authority(self):
        root = self.copy()
        current = root / "selected-state-transport"
        for name in ("product-resume-inputs", "product-resume-state", "runtime-state"):
            path = current / "original" / name / "raw-original"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"explicit synthetic external transport; not state admission\n")
        (current / "capture-transport.json").write_bytes(canonical_json_bytes({
            "captureProducer": self.source.base.producer, "stateWave": 4,
            "artifact": {"id": 700}, "observed": [{"synthetic": True}],
        }))
        before = regular_file_inventory(root, allow_empty=True)
        with patch("reuse.api_request", side_effect=AssertionError("re-observation")), self.read(root) as verified:
            self.assertEqual(before, verified["inventory"])
        (current / "unexpected").write_bytes(b"not in the fixed capture layout\n")
        with self.assertRaisesRegex(ValueError, "unexpected files"), self.read(root):
            self.fail("Unspecified current transport file accepted")


if __name__ == "__main__":
    unittest.main()
