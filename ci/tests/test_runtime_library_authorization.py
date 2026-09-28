"""Synthetic signed original closure, not hosted release authority."""

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from ci import runtime_phase10_library_caller as caller
from ci.tests import test_runtime_aggregate_handoff as fixture
from products.inventory import load_canonical_json_bytes, public_key_fingerprint, sha256_bytes, snapshot_regular_tree
from products.registry import NATIVE_TARGETS
from products.runtime_library_authorization import verified_runtime_libraries
from products.sdk_runtime_root import verify_external_library_authorization
from products.signatures import generate_development_key


class RuntimeLibraryAuthorizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.RuntimeAggregateHandoffTest.setUpClass()
        cls.addClassCleanup(fixture.RuntimeAggregateHandoffTest.doClassCleanups)
        cls.source = fixture.RuntimeAggregateHandoffTest()
        cls.source.setUp()
        cls.addClassCleanup(cls.source.doCleanups)
        policy = cls.source.source.policy
        cls.signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        cls.signing.update(policy["activeKey"])

    def test_signed_originals_project_exact_five_libraries_and_identities(self):
        with self.source.read() as verified:
            projected = verified_runtime_libraries(verified, self.signing)
            self.assertEqual(set(NATIVE_TARGETS), set(projected))
            for target, item in projected.items():
                claim = item["claim"]
                self.assertEqual(target, claim["runtimeIdentity"]["target"])
                self.assertEqual("0.2.7", claim["runtimeVersion"])
                self.assertEqual(sha256_bytes(item["library"]), claim["runtimeLibrarySha256"])
                self.assertTrue(item["fileName"])

    def test_observation_token_rejected_before_handoff_or_signing(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-token-negative-") as temporary:
            destination = Path(temporary) / "unauthorized"
            with patch.dict(os.environ, {"GITHUB_TOKEN": "observation-token"}), \
                    patch.object(caller, "verified_runtime_aggregate_handoff") as gate, \
                    patch.object(caller, "issue_root_delegation") as signer, \
                    self.assertRaisesRegex(ValueError, "observation token"):
                caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, destination,
                    expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                    expected_build_key="sha256:" + "b" * 64,
                    keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=Path(temporary) / "missing-root.pub",
                    expected_root_fingerprint="sha256:" + "c" * 64,
                    root_private_key=Path(temporary) / "missing-root-key",
                    release_private_key=Path(temporary) / "missing-release-key",
                )
            gate.assert_not_called()
            signer.assert_not_called()
            self.assertFalse(destination.exists())

    def test_protected_caller_signs_exact_external_bytes_after_full_handoff(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-authorization-test-") as temporary:
            work = Path(temporary).resolve()
            root_private, root_public, _ = generate_development_key(work / "root")
            fingerprint = public_key_fingerprint(root_public.read_bytes())
            receipt = load_canonical_json_bytes(
                (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes())
            arguments = dict(
                expected_metadata_receipt_sha256=sha256_bytes(
                    (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes()),
                expected_build_key=receipt["buildKey"], keyring=self.source.keyring,
                keys_directory=self.source.keys, root_public_key=root_public,
                expected_root_fingerprint=fingerprint, root_private_key=root_private,
                release_private_key=self.source.source.context["private_key"],
            )
            destination = work / "released"
            with patch.object(caller, "verified_runtime_aggregate_handoff",
                              wraps=caller.verified_runtime_aggregate_handoff) as gate:
                result = caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, destination, **arguments)
            gate.assert_called_once()
            self.assertEqual(fingerprint, result["rootFingerprint"])
            compatibility = load_canonical_json_bytes(self.source.source.chain["compatibility"].read_bytes())
            for target in NATIVE_TARGETS:
                paths = list((destination / target).glob("libcodex_agent.*")) + \
                    list((destination / target).glob("codex_agent.dll"))
                libraries = [path for path in paths if path.is_file()]
                self.assertEqual(1, len(libraries), target)
                library = libraries[0]
                claim = verify_external_library_authorization(
                    library.with_name(library.name + ".evidence"),
                    sdk_pinned_root_public_key=root_public.read_bytes(),
                    sdk_compatibility=compatibility, target=target, library_snapshot=library,
                )
                self.assertEqual(sha256_bytes(library.read_bytes()), claim["runtimeLibrarySha256"])
            with patch.object(caller, "issue_root_delegation") as signer, \
                    self.assertRaisesRegex(ValueError, "caller pin"):
                caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, work / "wrong-root", **{
                        **arguments, "expected_root_fingerprint": sha256_bytes(b"wrong"),
                    })
            signer.assert_not_called()
            self.assertFalse((work / "wrong-root").exists())

    def test_corrupt_original_variant_signature_cannot_reach_private_keys_or_publish(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-corrupt-original-") as temporary:
            work = Path(temporary).resolve()
            corrupt = work / "corrupt-original"
            snapshot_regular_tree(self.source.carrier, corrupt, allow_empty=True)
            signatures = list((corrupt / "variant-inputs/macos-arm64").glob("*.attestation.sig"))
            self.assertEqual(1, len(signatures))
            signatures[0].write_bytes(signatures[0].read_bytes() + b"x")
            receipt = (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes()
            root_public = Path(__file__).resolve().parents[2] / "gradle/release/keys/sdk-runtime-root.pub"
            destination = work / "unauthorized"
            with patch.object(caller, "issue_root_delegation", side_effect=AssertionError("root key reached")) as signer, \
                    self.assertRaises(ValueError):
                caller.produce_authenticated_runtime_libraries(
                    corrupt, destination,
                    expected_metadata_receipt_sha256=sha256_bytes(receipt),
                    expected_build_key=load_canonical_json_bytes(receipt)["buildKey"],
                    keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=root_public,
                    expected_root_fingerprint=public_key_fingerprint(root_public.read_bytes()),
                    root_private_key=work / "no-root-private-key",
                    release_private_key=work / "no-release-private-key",
                )
            signer.assert_not_called()
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
