"""Full signed synthetic aggregate carrier reads; never hosted/source execution."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_release as fixture
from products import runtime_aggregate_handoff as reader
from products.inventory import canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from products.receipt import verify_output_manifest_identity
from products.plan import NATIVE_RUNTIME_EVIDENCE_KEYS
from products.plan import _native_runtime_projection_from_record
from products.contract_projection import verify_contract_component_projection
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
            native_evidence = verified["nativeRuntimeEvidence"]
            self.assertEqual(list(NATIVE_TARGETS), list(native_evidence))
            for target, record in native_evidence.items():
                self.assertEqual(NATIVE_RUNTIME_EVIDENCE_KEYS, set(record))
                self.assertEqual(target, record["target"])
                self.assertEqual({"binary", "package", "validation", "metadata"}, set(record["phaseReceipts"]))
                self.assertEqual(verified["directory"] / "runtime-stages", Path(record["stageRoot"]))
                for phase, path in record["phaseReceipts"].items():
                    self.assertTrue(Path(path).is_relative_to(verified["directory"]))
                    self.assertEqual(verified["receiptBytes"][PhaseInstanceId("runtime", target, phase, target)],
                                     Path(path).read_bytes())
                inputs = verified["indexInputs"]
                for name, existing in (("payload", "variant_bundles"), ("attestation", "variant_attestations"),
                                       ("attestationSignature", "variant_attestation_signatures"),
                                       ("publicKey", "variant_public_keys")):
                    self.assertEqual(inputs[existing][target], Path(record[name]))
                    self.assertTrue(Path(record[name]).is_relative_to(verified["directory"]))
                self.assertEqual(inputs["keyring"], Path(record["keyring"]))
                self.assertEqual(inputs["keys_directory"], Path(record["keysDirectory"]))
                self.assertTrue(Path(record["keyring"]).is_relative_to(verified["directory"].parent / "policy"))
                self.assertEqual(self.keyring.read_bytes(), Path(record["keyring"]).read_bytes())
                self.assertEqual(regular_file_inventory(self.keys), regular_file_inventory(Path(record["keysDirectory"])))
            phases = verified["originalPhases"]
            expected = {PhaseInstanceId(*(record[name] for name in ("product", "component", "phase", "target")))
                        for record in self.source.selection["originals"]}
            self.assertEqual(50, len(phases))
            self.assertEqual(expected, set(phases))
            self.assertEqual(set(verified["receipts"]), set(phases))
            for identity, original in phases.items():
                self.assertEqual({"stage", "receiptPath", "receipt"}, set(original))
                self.assertIs(original["receipt"], verified["receipts"][identity])
                for name in ("stage", "receiptPath"):
                    self.assertTrue(original[name].is_relative_to(verified["directory"]))
                self.assertEqual(verified["receiptBytes"][identity], original["receiptPath"].read_bytes())
                retained_path = self.carrier / original["receiptPath"].relative_to(verified["directory"])
                self.assertEqual(retained_path.read_bytes(), original["receiptPath"].read_bytes())
                output_manifest = verify_output_manifest_identity(original["stage"],
                    identity.product, identity.component, identity.phase, identity.target,
                    original["receipt"]["productVersion"])
                self.assertEqual(original["receipt"]["outputs"], output_manifest["outputs"])
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
                for record in verified["nativeRuntimeEvidence"].values():
                    self.assertEqual(keyring.read_bytes(), Path(record["keyring"]).read_bytes())
                    self.assertNotEqual(self.keyring.read_bytes(), Path(record["keyring"]).read_bytes())
        finally:
            hidden.rename(self.carrier)

    def test_release_native_projection_accepts_separately_authenticated_development_contract(self):
        # The chain's original development attestation and the carrier's release
        # attestation authenticate the same Contract bytes independently. A
        # current development consumer must not relabel its retained Runtime.
        target = "linux-x64"
        contract = self.source.chain["contract"]
        stage = self.source.chain["root"] / "contract-source/metadata-stage"
        before = regular_file_inventory(self.carrier, allow_empty=True)
        with patch("reuse.api_request", side_effect=AssertionError("mixed-trust read contacted CI")), \
                patch("products.runtime_aggregate.sign_manifest", side_effect=AssertionError("mixed-trust read signed")):
            projection = verify_contract_component_projection(
                stage, contract["receipt"], contract["attestation"], contract["signature"],
                self.source.context["public_key"], expected_trust_domain="development",
                expected_contract_version="0.2.0", required_components=("common", target))
            with self.read() as verified:
                record = verified["nativeRuntimeEvidence"][target]
                proof = _native_runtime_projection_from_record(record, projection, contract["payload"], "release")
                receipt = verified["receipts"][PhaseInstanceId("runtime", target, "validation", target)]
                value = proof.receipt_value(receipt, projection)
                from products.inventory import sha256_bytes
                self.assertEqual(sha256_bytes(verified["receiptBytes"][PhaseInstanceId("runtime", target, "validation", target)]),
                                 value["receiptSha256"])
                self.assertEqual(target, proof.target)
                self.assertEqual(str(verified["indexInputs"]["keyring"]), record["keyring"])
                # Conversely, the current Contract's development domain is not
                # permission to accept the release Runtime as development.
                with self.assertRaises(ValueError):
                    _native_runtime_projection_from_record(record, projection, contract["payload"], "development")
        self.assertEqual(before, regular_file_inventory(self.carrier, allow_empty=True))

    def test_context_index_inputs_reuse_real_admission_and_preserve_exact_private_originals(self):
        from products.index import IndexEntrySource, ReleaseIndexAdmission, release_attested_runtime_aggregate_admission

        instance = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        before = regular_file_inventory(self.carrier, allow_empty=True)
        with patch("products.runtime_aggregate.sign_manifest", side_effect=AssertionError("index extraction signed")), \
                patch("reuse.api_request", side_effect=AssertionError("index extraction contacted CI")), \
                self.read() as verified:
            arguments = verified["indexInputs"]
            self.assertEqual({"manifest", "metadata_receipt", "attestation", "signature", "public_key",
                "variant_bundles", "variant_phase_receipts", "variant_attestations", "variant_attestation_signatures",
                "variant_public_keys", "variant_validation_evidence", "adapter_receipts", "keyring", "keys_directory",
                "variant_keyring", "variant_keys_directory"}, set(arguments))
            policy_fields = {"keyring", "keys_directory", "variant_keyring", "variant_keys_directory"}

            def paths(value):
                if isinstance(value, Path):
                    yield value
                elif isinstance(value, dict):
                    for member in value.values():
                        yield from paths(member)
                elif isinstance(value, list):
                    for member in value:
                        yield from paths(member)

            for name, value in arguments.items():
                for path in paths(value):
                    base = verified["directory"].parent / "policy" if name in policy_fields else verified["directory"]
                    self.assertTrue(path.is_relative_to(base), (name, path))
            self.assertEqual(self.keyring.read_bytes(), arguments["keyring"].read_bytes())
            self.assertEqual(arguments["keyring"], arguments["variant_keyring"])
            self.assertEqual(arguments["keys_directory"], arguments["variant_keys_directory"])
            self.assertEqual(5, len(arguments["variant_bundles"]))
            self.assertEqual(20, sum(len(value) for value in arguments["variant_phase_receipts"].values()))
            self.assertEqual(25, len(arguments["adapter_receipts"]))
            raw = verified["receiptBytes"][instance]
            self.assertEqual(raw, arguments["metadata_receipt"].read_bytes())
            self.assertEqual((self.carrier / "aggregate-input/metadata-receipt.json").read_bytes(), raw)
            output, = (record for record in verified["receipts"][instance]["outputs"] if record["kind"] == "runtime-aggregate")
            source = IndexEntrySource(raw, output["relativePath"])
            admission = release_attested_runtime_aggregate_admission(source, **arguments)
            self.assertIsInstance(admission, ReleaseIndexAdmission)
            private = verified["directory"]
        self.assertFalse(private.exists())
        self.assertEqual(before, regular_file_inventory(self.carrier, allow_empty=True))

        # Even after full verification, private input changes must fail the
        # enclosing context. Callers must wait for this exit before publication.
        with self.assertRaisesRegex(ValueError, "changed during verification"), self.read() as verified:
            receipt = verified["indexInputs"]["metadata_receipt"]
            receipt.write_bytes(receipt.read_bytes() + b"\n")
        self.assertEqual(before, regular_file_inventory(self.carrier, allow_empty=True))

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
            root / "original-evidence/transport/original-ci-phases.json",
            root / "original-evidence/transport/original-ci-phases.sig",
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
            "captureProducer": self.source.base.producer, "stateWave": 5,
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
