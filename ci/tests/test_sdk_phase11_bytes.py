"""Offline SDK Phase-11 signed-campaign forwarding; hosted approval stays external."""

from contextlib import contextmanager, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from ci import sdk_phase11_bytes as candidate
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file


class SdkPhase11BytesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.capture = self.root / "phase10"
        pair = self.capture / "signed-pair"
        pair.mkdir(parents=True)
        self.evidence = self.capture / "replay-evidence"
        self.evidence.mkdir()
        keys = self.evidence / "keys"
        keys.mkdir()
        (keys / "release.pub").write_bytes(b"release public key\n")
        self.commit, self.tree = "a" * 40, "b" * 40
        self.original = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "event": "pull_request",
            "commit": self.commit, "tree": self.tree, "runId": 41,
            "runAttempt": 2, "pullRequest": 31}
        self.authority_producer = {**self.original, "event": "workflow_dispatch",
            "runId": 77, "pullRequest": None}
        self.record_producer = {**self.authority_producer, "runId": 88}
        self.index_bytes = b'{"verified":"release index"}\n'
        self.signature_bytes = b"original detached signature\n"
        (pair / "product-index.json").write_bytes(self.index_bytes)
        (pair / "product-index.sig").write_bytes(self.signature_bytes)
        (self.evidence / "product-signing-keys.json").write_bytes(b"original keyring\n")
        (self.evidence / "sdk-campaign-authority.json").write_bytes(b"approved authority\n")
        self.authority = {"sdkVersion": "0.8.0",
            "completedCatalogPin": {"producer": self.original},
            "electionSha256": {}, "semanticSha256": {}}
        for kind in ("election", "semantic"):
            for family in ("core-android", "native", "apple-js"):
                payload = f"{kind}-{family}\n".encode()
                (self.evidence / f"{kind}-{family}.json").write_bytes(payload)
                self.authority[f"{kind}Sha256"][family] = sha256_bytes(payload)
        self._zip(self.capture / "official-upload.zip", {
            "product-index.json": self.index_bytes,
            "product-index.sig": self.signature_bytes})
        self._zip(self.evidence / "authority-upload.zip", {
            "sdk-campaign-authority.json": b"approved authority\n"})
        (self.evidence / "authority-transport.json").write_bytes(canonical_json_bytes({
            "originalProducer": self.original, "authorityProducer": self.authority_producer,
            "artifactSha256": sha256_file(self.evidence / "authority-upload.zip"),
            "authoritySha256": sha256_file(self.evidence / "sdk-campaign-authority.json"),
        }))
        (self.capture / "transport.json").write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "originalProducer": self.original,
            "recordProducer": self.record_producer, "recordObservation": {},
            "artifact": {"digest": sha256_file(self.capture / "official-upload.zip")},
        }))
        self.destination = self.root / "candidate"

    @staticmethod
    def _zip(path, files):
        with ZipFile(path, "w") as archive:
            for name, data in files.items():
                archive.writestr(name, data)

    def kwargs(self):
        return dict(
            landed_repository=self.checkout,
            expected_inventory_sha256=candidate._inventory_digest(self.capture),
            expected_index_sha256=sha256_bytes(self.index_bytes),
            expected_signature_sha256=sha256_bytes(self.signature_bytes),
            expected_authority_sha256=sha256_file(self.evidence / "sdk-campaign-authority.json"),
            expected_signed_upload_sha256=sha256_file(self.capture / "official-upload.zip"),
            expected_authority_upload_sha256=sha256_file(self.evidence / "authority-upload.zip"),
            expected_authority_transport_sha256=sha256_file(self.evidence / "authority-transport.json"),
            expected_keyring_sha256=sha256_file(self.evidence / "product-signing-keys.json"),
            expected_keys_inventory_sha256=candidate._inventory_digest(self.evidence / "keys"),
            expected_sdk_version="0.8.0", expected_source_commit=self.commit,
            expected_source_tree=self.tree, expected_validation_tree=self.tree,
        )

    def forward(self, *, cli=False, trees=None, authority_exit_error=False, **changes):
        @contextmanager
        def authority(path, digest):
            self.assertEqual(self.evidence.joinpath("sdk-campaign-authority.json").read_bytes(),
                             path.read_bytes())
            self.assertEqual(digest, sha256_file(path))
            yield self.authority
            if authority_exit_error:
                raise ValueError("SDK campaign authority changed during replay")

        def verify(signed, *, keyring_path, keys_directory):
            self.assertEqual(self.index_bytes, signed.manifest.read_bytes())
            self.assertEqual(self.signature_bytes, signed.signature.read_bytes())
            self.assertEqual(b"original keyring\n", keyring_path.read_bytes())
            self.assertEqual(regular_file_inventory(self.evidence / "keys"),
                             regular_file_inventory(keys_directory))
            index = {"trustDomain": "release", "producer": self.original,
                "repository": self.original["repository"],
                "context": {"kind": "pull-request", "pullRequest": 31,
                    **{name: self.original[name] for name in (
                        "commit", "tree", "runId", "runAttempt")}},
                "entries": [{"productVersion": "0.8.0"}] * 61}
            return index, self.index_bytes

        with patch.object(candidate, "_landed_tree", side_effect=trees or (lambda _: self.tree)), \
                patch.object(candidate, "held_pinned_sdk_campaign_authority", side_effect=authority), \
                patch.object(candidate, "verify_release_product_index", side_effect=verify) as signed:
            if cli:
                values = {"protected_capture": self.capture, "destination": self.destination,
                          **self.kwargs(), **changes}
                args = [item for name, value in values.items()
                        for item in ("--" + name.replace("_", "-"), str(value))]
                with redirect_stdout(StringIO()) as output:
                    self.assertEqual(0, candidate.main(args))
                result = json.loads(output.getvalue())
            else:
                result = candidate.forward_verified_sdk_phase10_bytes(
                    self.capture, self.destination, **{**self.kwargs(), **changes})
        signed.assert_called_once()
        return result

    def test_forwards_exact_phase10_evidence_and_cli(self):
        result = self.forward(cli=True)
        self.assertEqual("0.8.0", result["sdkVersion"])
        self.assertEqual(regular_file_inventory(self.capture),
                         regular_file_inventory(self.destination))
        self.assertEqual(self.index_bytes,
                         (self.destination / "signed-pair/product-index.json").read_bytes())

    def test_wrong_independent_pin_or_landed_tree_rejects_without_output(self):
        with self.assertRaisesRegex(ValueError, "independently selected bytes"):
            self.forward(expected_inventory_sha256=sha256_bytes(b"different"))
        with self.assertRaisesRegex(ValueError, "landed tree differs"):
            self.forward(expected_validation_tree="d" * 40)
        self.assertFalse(self.destination.exists())

    def test_repacked_signed_upload_or_policy_mutation_rejects(self):
        original_upload = (self.capture / "official-upload.zip").read_bytes()
        original_transport = (self.capture / "transport.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "official upload differs"):
            self._zip(self.capture / "official-upload.zip", {
                "product-index.json": b"different index\n",
                "product-index.sig": self.signature_bytes})
            (self.capture / "transport.json").write_bytes(canonical_json_bytes({
                "schemaVersion": 1, "originalProducer": self.original,
                "recordProducer": self.record_producer, "recordObservation": {},
                "artifact": {"digest": sha256_file(self.capture / "official-upload.zip")},
            }))
            self.forward(expected_inventory_sha256=candidate._inventory_digest(self.capture),
                expected_signed_upload_sha256=sha256_file(self.capture / "official-upload.zip"))
        self.assertFalse(self.destination.exists())
        (self.capture / "official-upload.zip").write_bytes(original_upload)
        (self.capture / "transport.json").write_bytes(original_transport)
        (self.evidence / "election-native.json").write_bytes(b"changed policy\n")
        with self.assertRaisesRegex(ValueError, "policy differs"):
            self.forward(expected_inventory_sha256=candidate._inventory_digest(self.capture),
                expected_signed_upload_sha256=sha256_file(self.capture / "official-upload.zip"))
        self.assertFalse(self.destination.exists())

    def test_phase10_capture_mutation_after_snapshot_rejects(self):
        old = candidate.snapshot_regular_tree

        def mutate(source, destination):
            old(source, destination)
            (source / "transport.json").write_bytes(b"changed transport\n")

        with patch.object(candidate, "snapshot_regular_tree", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed during verification"):
            self.forward()
        self.assertFalse(self.destination.exists())

    def test_landed_tree_changes_before_publication_without_output(self):
        with patch.object(candidate, "publish_regular_tree") as publish, \
                self.assertRaisesRegex(ValueError, "changed during verification"):
            self.forward(trees=[self.tree, "d" * 40])
        publish.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_authority_exit_failure_cannot_leave_candidate_output(self):
        with patch.object(candidate, "publish_regular_tree") as publish, \
                self.assertRaisesRegex(ValueError, "authority changed during replay"):
            self.forward(authority_exit_error=True)
        publish.assert_not_called()
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
