"""No-secret preparation orchestration, not signing or original-proof acceptance.

The original validation context is mocked. Receipts, snapshots, inventories and
the no-secret boundary are real; no native tooling or network is invoked.
"""

from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_ios_original_validation as preparation
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.tests import test_sdk_apple_validation_inputs as fixtures


SECRET = "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"


class AppleSigningPreparationTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AppleValidationInputsTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.capture = self.fixture.entry() / "capture"
        self.raw = (self.capture / "original/shard/phase-receipt.json").read_bytes()
        self.receipt = json.loads(self.raw)
        self.receipt_path = self.root / "selected-receipt.json"
        self.receipt_path.write_bytes(self.raw)
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b'{"fixture":"caller original plan"}\n')
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.destination = self.root / "output"
        self.environment = {"GITHUB_EVENT_NAME": "pull_request"}
        self.arguments = dict(target="ios-arm64", expected_receipt_sha256=sha256_bytes(self.raw),
            artifact_id=91, artifact_sha256="sha256:" + "9" * 64, trusted_workflow_sha="a" * 40,
            repository_root=self.repository, environ=self.environment, token="fixture-token",
            policy_revision="b" * 40, required_trust_domain="release")
        for name in ("keyring", "keys_directory", "tooling_evidence", "tooling_public_key", "java_executable",
                     "tooling_keyring", "tooling_keys_directory"):
            path = self.root / "caller-policy" / name
            if name in ("keys_directory", "tooling_evidence", "tooling_keys_directory"):
                path.mkdir(parents=True)
                (path / "retained").write_bytes(b"caller-owned public input\n")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"caller-owned public input\n")
            self.arguments[name] = path
        self.events = []
        self.mutation = None
        self.environment_patch = patch.dict(os.environ, {}, clear=True)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)
        self.reader_patch = patch.object(preparation, "verified_original_ios_validation", side_effect=self.original)
        self.reader = self.reader_patch.start()
        self.addCleanup(self.reader_patch.stop)
        snapshot = preparation.snapshot_regular_tree

        def capture_copy(source, destination, **arguments):
            snapshot(source, destination, **arguments)
            if Path(source) == self.capture:
                self.private_capture = Path(destination)

        self.snapshot_patch = patch.object(preparation, "snapshot_regular_tree", side_effect=capture_copy)
        self.snapshot_patch.start()
        self.addCleanup(self.snapshot_patch.stop)

    @contextmanager
    def original(self, plan, receipt_path, **arguments):
        self.events.append("enter")
        self.assertEqual(self.plan.read_bytes(), Path(plan).read_bytes())
        self.assertEqual(self.raw, Path(receipt_path).read_bytes())
        expected = {key: value for key, value in self.arguments.items() if key not in ("target", "expected_receipt_sha256")}
        self.assertEqual(expected, arguments)
        self.assertFalse(self.destination.exists())
        yield {"capture": self.capture, "receiptBytes": self.raw, "receipt": deepcopy(self.receipt)}
        self.events.append("exit")
        self.assertFalse(self.destination.exists())
        if self.mutation == "exit-error":
            raise ValueError("original context exit rejected")
        if self.mutation == "private-capture":
            (self.private_capture / "original/empty.log").write_bytes(b"late capture change")
        elif self.mutation == "plan":
            self.plan.write_bytes(b"late plan change")
        elif self.mutation == "receipt":
            self.receipt_path.write_bytes(b"late selected receipt change")
        elif self.mutation == "caller-secret":
            self.environment[SECRET] = ""
        elif self.mutation == "live-secret":
            os.environ[SECRET] = ""

    def invoke(self, **changes):
        return preparation.prepare_ios_validation_signing_inputs(self.plan, self.receipt_path, self.destination,
                                                                 **{**self.arguments, **changes})

    def test_exact_forwarding_full_capture_preservation_and_publication_only_after_context_exit(self):
        before = regular_file_inventory(self.capture, allow_empty=True)
        plan_raw = self.plan.read_bytes()
        expected = {"schemaVersion": 1, "target": self.arguments["target"], "receiptSha256": sha256_bytes(self.raw),
            "captureDigest": sha256_bytes(canonical_json_bytes(before)), "planSha256": sha256_bytes(plan_raw),
            "originalArtifact": {"artifactId": 91, "artifactSha256": "sha256:" + "9" * 64},
            "producer": self.receipt["producer"]}
        self.assertEqual(expected, self.invoke())
        self.assertEqual(["enter", "exit"], self.events)
        self.assertEqual({"capture", "preparation.json"}, {path.name for path in self.destination.iterdir()})
        self.assertEqual(expected, json.loads((self.destination / "preparation.json").read_bytes()))
        self.assertEqual(before, regular_file_inventory(self.destination / "capture", allow_empty=True))
        self.assertEqual(before, regular_file_inventory(self.capture, allow_empty=True))
        self.assertEqual(self.raw, self.receipt_path.read_bytes())
        self.assertEqual(plan_raw, self.plan.read_bytes())
        self.assertNotIn("signing", expected)
        self.assertNotIn("token", expected)

    def test_simulator_preserves_its_own_exact_original_identity(self):
        self.capture = self.fixture.entry("simulator", "ios-simulator-arm64") / "capture"
        self.raw = (self.capture / "original/shard/phase-receipt.json").read_bytes()
        self.receipt = json.loads(self.raw)
        self.receipt_path.write_bytes(self.raw)
        self.arguments.update(target="ios-simulator-arm64", expected_receipt_sha256=sha256_bytes(self.raw))
        self.test_exact_forwarding_full_capture_preservation_and_publication_only_after_context_exit()

    def test_exit_failure_capture_plan_receipt_mutation_and_late_secret_prevent_publication(self):
        originals = {path: path.read_bytes() for path in (self.plan, self.receipt_path, self.capture / "original/empty.log")}
        for mutation in ("exit-error", "private-capture", "plan", "receipt", "caller-secret", "live-secret"):
            self.mutation = mutation
            try:
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    self.invoke()
                self.assertFalse(self.destination.exists())
            finally:
                for path, raw in originals.items():
                    path.write_bytes(raw)
                self.environment.pop(SECRET, None)
                os.environ.pop(SECRET, None)

    def test_secret_even_empty_in_either_environment_rejects_before_original_replay(self):
        for location in (self.environment, os.environ):
            for value in ("", "fixture-secret"):
                location[SECRET] = value
                try:
                    with self.subTest(live=location is os.environ, value=value), self.assertRaises(ValueError):
                        self.invoke()
                    self.reader.assert_not_called()
                    self.assertFalse(self.destination.exists())
                finally:
                    location.pop(SECRET, None)

    def test_malformed_selection_and_nonrelease_tooling_reject_before_reader(self):
        for changes in ({"target": "ios"}, {"target": "ios-simulator-arm64"},
                        {"expected_receipt_sha256": "not-a-digest"},
                        {"expected_receipt_sha256": "sha256:" + "0" * 64},
                        {"artifact_id": True}, {"artifact_sha256": "invalid"},
                        {"required_trust_domain": "development"}, {"tooling_keyring": None},
                        {"tooling_keys_directory": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.invoke(**changes)
            self.reader.assert_not_called()
            self.assertFalse(self.destination.exists())

    def test_output_overlap_existing_and_symlink_ancestry_preserve_original_inputs(self):
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "sentinel").write_bytes(b"keep")
        alias = self.root / "alias"
        alias.symlink_to(occupied, target_is_directory=True)
        for destination in (self.repository / "output", self.plan, self.receipt_path,
                            self.arguments["tooling_evidence"] / "output", occupied, alias / "output"):
            self.destination = destination
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.invoke()
            self.reader.assert_not_called()
        self.assertEqual(b"keep", (occupied / "sentinel").read_bytes())
        self.assertFalse((occupied / "output").exists())
