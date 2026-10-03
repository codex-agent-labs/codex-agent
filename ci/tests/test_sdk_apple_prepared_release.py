"""Real prepared binding, release signatures and storage behind mocked authority.

Only Git/source authorization and upload capture are synthetic. These tests do
not prove hosted identity, protected environment approval or native execution.
"""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

from ci import sdk_apple_prepared_release as release
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, snapshot_regular_tree, write_canonical_json
from ci.products.sdk_apple_validation_inputs import load_sdk_apple_validation_evidence
from ci.products.sdk_apple_validation_attestation import verified_apple_validation_attestation
from ci.products.signatures import generate_development_key
from ci.tests import test_sdk_apple_prepared_binding as fixtures


SECRET = "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen required")
class ApplePreparedReleaseTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ApplePreparedBindingTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.trusted, self.candidate = self.root / "trusted", self.root / "candidate"
        self.trusted.mkdir()
        self.candidate.mkdir()
        self.destination = self.root / "published"
        self.private_key, self.public_key, signing = generate_development_key(self.root / "ephemeral")
        self.key_id = "release-fixture"
        self.ring = {"schemaVersion": 1, "algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
                     "trustDomain": "release", "activeKey": {"keyId": self.key_id, "fingerprint": signing["fingerprint"]},
                     "retiredKeys": []}
        self.producer = {**self.fixture.fixture.producer, "commit": "c" * 40, "tree": "d" * 40, "runId": 92}
        self.environment = {SECRET: self.private_key.read_text(), "GITHUB_RUN_ID": "92", "GITHUB_RUN_ATTEMPT": "2"}
        self.plan_value = {"remoteBuildAuthorized": True, "event": "pull_request", "validationCommit": self.producer["commit"]}
        self.arguments = dict(target="ios-arm64", expected_receipt_sha256=self.fixture.arguments["expected_receipt_sha256"],
            artifact_id=91, artifact_sha256=self.fixture.arguments["artifact_sha256"],
            preparation_artifact_id=101, preparation_artifact_sha256="sha256:" + "1" * 64,
            trusted_source_sha="e" * 40, trusted_workflow_sha="f" * 40, transport_producer=self.producer,
            event_payload={"number": 31}, environment=self.environment, token="fixture-token")
        self.captures = {}
        self.context = self.mock("verify_product_release_context", return_value=(
            self.trusted, self.producer, "9" * 40, {"GITHUB_RUN_ID": "92", "GITHUB_RUN_ATTEMPT": "2"},
            "synthetic source authorization"))
        self.validate = self.mock("_validate_plan", side_effect=self.validate_plan)
        self.consumer = self.mock("_consumer", return_value={"producer": self.producer})
        self.prepare = self.mock("capture_apple_signing_preparation", side_effect=self.capture_preparation)
        self.original = self.mock("capture_sdk_ios_validation_upload", side_effect=self.capture_original)
        # Keep _release_trust and all keyring checks real; only immutable Git
        # object reads substitute fixture bytes for a genuine source checkout.
        source_module = sys.modules[release._release_trust.__module__]
        trees = patch.object(source_module, "tree_entries", return_value=[
            ("gradle/release/product-signing-keys.json", "100644"),
            (f"gradle/release/keys/{self.key_id}.pub", "100644")])
        blobs = patch.object(source_module, "git_regular_blob_bytes", side_effect=self.git_blob)
        trees.start()
        blobs.start()
        self.addCleanup(trees.stop)
        self.addCleanup(blobs.stop)

    def mock(self, name, **kwargs):
        mocked = patch.object(release, name, **kwargs)
        value = mocked.start()
        self.addCleanup(mocked.stop)
        return value

    def git_blob(self, root, revision, path, **kwargs):
        self.assertEqual(self.trusted, root)
        self.assertEqual(self.arguments["trusted_source_sha"], revision)
        if path == "gradle/release/product-signing-keys.json":
            return canonical_json_bytes(self.ring)
        self.assertEqual(f"gradle/release/keys/{self.key_id}.pub", path)
        return self.public_key.read_bytes()

    def validate_plan(self, path, root, **kwargs):
        self.assertEqual(self.candidate, root)
        self.assertEqual(self.fixture.plan.read_bytes(), Path(path).read_bytes())
        return dict(self.plan_value)

    def capture_preparation(self, plan, destination, **kwargs):
        self.assertEqual(self.fixture.plan.read_bytes(), Path(plan).read_bytes())
        self.assertEqual(dict(target="ios-arm64", artifact_id=101, artifact_sha256="sha256:" + "1" * 64,
            trusted_workflow_sha="f" * 40, repository_root=self.candidate, environ=self.invocation_environment,
            token="fixture-token"), kwargs)
        snapshot_regular_tree(self.fixture.prepared, destination / "original", allow_empty=True)
        (destination / "original-upload.zip").write_bytes(b"opaque preparation upload transport seam\n")
        transport = {"artifact": {"id": 101, "digest": "sha256:" + "1" * 64}, "captureProducer": self.producer,
                     "target": "ios-arm64", "observed": []}
        write_canonical_json(destination / "capture-transport.json", transport)
        self.captures["preparation"] = destination
        return transport

    def capture_original(self, plan, destination, **kwargs):
        self.assertEqual(self.fixture.plan.read_bytes(), Path(plan).read_bytes())
        self.assertEqual(self.fixture.raw, Path(kwargs.pop("validation_receipt_path")).read_bytes())
        self.assertEqual(dict(artifact_id=91, artifact_sha256=self.arguments["artifact_sha256"],
            trusted_workflow_sha="f" * 40, repository_root=self.candidate, environ=self.invocation_environment,
            token="fixture-token"), kwargs)
        snapshot_regular_tree(self.fixture.original, destination, allow_empty=True)
        self.captures["validation"] = destination
        return {"captureProducer": self.fixture.fixture.producer}

    def invoke(self, **changes):
        self.invocation_environment = changes.get("environment", self.environment)
        return release.attest_prepared_apple_validation_ci(self.trusted, self.candidate,
            self.fixture.plan, self.fixture.receipt, self.destination, **{**self.arguments, **changes})

    def test_real_release_signature_preserves_prepared_capture_receipt_and_both_transports(self):
        before = regular_file_inventory(self.fixture.capture, allow_empty=True)
        result = self.invoke()
        self.assertEqual({"sdk-apple-validation-evidence", "preparation-transport", "validation-transport",
                          "caller-policy", "caller.json"}, {path.name for path in self.destination.iterdir()})
        self.assertEqual(result, json.loads((self.destination / "caller.json").read_bytes()))
        self.assertEqual({"schemaVersion", "target", "trustedSourceCommit", "trustedSourceTree", "trustedWorkflowSha",
                          "transportProducer", "authorizationReason", "event", "receiptSha256",
                          "preparationArtifact", "originalArtifact"}, set(result))
        self.assertEqual(self.producer, result["transportProducer"])
        self.assertEqual(self.arguments["expected_receipt_sha256"], result["receiptSha256"])
        self.assertEqual({"artifactId": 101, "artifactSha256": "sha256:" + "1" * 64}, result["preparationArtifact"])
        self.assertEqual({"artifactId": 91, "artifactSha256": self.arguments["artifact_sha256"]}, result["originalArtifact"])
        self.assertEqual("e" * 40, result["trustedSourceCommit"])
        self.assertEqual("9" * 40, result["trustedSourceTree"])
        self.assertEqual("f" * 40, result["trustedWorkflowSha"])
        self.assertEqual({"number": 31}, result["event"])
        self.assertEqual(regular_file_inventory(self.fixture.prepared, allow_empty=True),
            regular_file_inventory(self.destination / "preparation-transport/original", allow_empty=True))
        self.assertEqual(regular_file_inventory(self.fixture.original, allow_empty=True),
            regular_file_inventory(self.destination / "validation-transport", allow_empty=True))
        carrier = self.destination / "sdk-apple-validation-evidence"
        records = load_sdk_apple_validation_evidence(carrier)
        self.assertEqual(1, len(records))
        entry = carrier / records[0]["evidenceRoot"]
        self.assertEqual(before, regular_file_inventory(entry / "capture", allow_empty=True))
        self.assertEqual(self.fixture.raw, (entry / "capture/original/shard/phase-receipt.json").read_bytes())
        public_policy = self.root / "verification-policy"
        (public_policy / "keys").mkdir(parents=True)
        (public_policy / "keys" / f"{self.key_id}.pub").write_bytes(self.public_key.read_bytes())
        write_canonical_json(public_policy / "keyring.json", self.ring)
        with verified_apple_validation_attestation(entry / "capture", self.fixture.receipt,
                entry / "apple-validation-attestation.json", entry / "apple-validation-attestation.sig",
                public_key=None, required_trust_domain="release", keyring=public_policy / "keyring.json",
                keys_directory=public_policy / "keys") as verified:
            self.assertEqual(self.fixture.raw, verified["receiptBytes"])
            self.assertEqual(self.key_id, verified["attestation"]["signing"]["keyId"])
        self.assertEqual(before, regular_file_inventory(self.fixture.capture, allow_empty=True))
        for row in regular_file_inventory(self.destination, allow_empty=True):
            self.assertNotIn(self.private_key.read_bytes(), (self.destination / row["relativePath"]).read_bytes())

    def test_wrong_current_plan_producer_target_receipt_and_malformed_preparation_do_not_sign(self):
        original_record = (self.fixture.prepared / "preparation.json").read_bytes()
        for failure in ("producer", "authorization", "target", "receipt", "record"):
            changes = {}
            self.consumer.return_value = {"producer": self.producer}
            self.plan_value["remoteBuildAuthorized"] = True
            if failure == "producer":
                self.consumer.return_value = {"producer": {**self.producer, "runAttempt": 3}}
            elif failure == "authorization":
                self.plan_value["remoteBuildAuthorized"] = False
            elif failure == "target":
                changes["target"] = "ios"
            elif failure == "receipt":
                changes["expected_receipt_sha256"] = "sha256:" + "0" * 64
            else:
                write_canonical_json(self.fixture.prepared / "preparation.json", {**self.fixture.record, "extra": True})
            try:
                with self.subTest(failure=failure), patch.object(release, "sign_manifest", wraps=release.sign_manifest) as sign:
                    with self.assertRaises(ValueError):
                        self.invoke(**changes)
                    sign.assert_not_called()
                self.assertFalse(self.destination.exists())
            finally:
                (self.fixture.prepared / "preparation.json").write_bytes(original_record)

    def test_missing_secret_or_active_release_key_never_signs_or_publishes(self):
        for failure in ("secret", "active"):
            environment = {key: value for key, value in self.environment.items() if key != SECRET} if failure == "secret" else self.environment
            original_ring = deepcopy(self.ring)
            if failure == "active":
                self.ring["activeKey"] = None
            try:
                with self.subTest(failure=failure), patch.object(release, "sign_manifest", wraps=release.sign_manifest) as sign:
                    with self.assertRaises(ValueError):
                        self.invoke(environment=environment)
                    sign.assert_not_called()
                self.assertFalse(self.destination.exists())
            finally:
                self.ring = original_ring

    def test_real_binding_exit_and_caller_input_mutations_after_signing_prevent_publication(self):
        original_sign = release.sign_manifest
        plan_raw, receipt_raw = self.fixture.plan.read_bytes(), self.fixture.receipt.read_bytes()
        for failure in ("prepared", "original", "plan", "receipt", "event", "environment"):
            def sign(*args, **kwargs):
                value = original_sign(*args, **kwargs)
                if failure == "event":
                    self.arguments["event_payload"]["number"] = 99
                elif failure == "environment":
                    self.environment["GITHUB_RUN_ID"] = "99"
                else:
                    target = {"prepared": self.captures["preparation"] / "original/capture/original/empty.log",
                              "original": self.captures["validation"] / "original/empty.log",
                              "plan": self.fixture.plan, "receipt": self.fixture.receipt}[failure]
                    target.write_bytes(b"mutation after successful signature")
                return value
            try:
                with self.subTest(failure=failure), patch.object(release, "sign_manifest", side_effect=sign):
                    with self.assertRaises(ValueError):
                        self.invoke()
                self.assertFalse(self.destination.exists())
            finally:
                self.fixture.plan.write_bytes(plan_raw)
                self.fixture.receipt.write_bytes(receipt_raw)
                self.arguments["event_payload"]["number"] = 31
                self.environment["GITHUB_RUN_ID"] = "92"

    def test_output_overlap_existing_and_symbolic_ancestry_reject_before_capture(self):
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "sentinel").write_bytes(b"keep")
        alias = self.root / "alias"
        alias.symlink_to(occupied, target_is_directory=True)
        for destination in (self.trusted / "out", self.candidate / "out", self.fixture.plan,
                            self.fixture.receipt, occupied, alias / "out"):
            self.destination = destination
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.invoke()
            self.prepare.assert_not_called()
            self.original.assert_not_called()
        self.assertEqual(b"keep", (occupied / "sentinel").read_bytes())

    def test_capture_mutation_rejects_before_signing_and_forwarded_carrier_mutation_never_publishes(self):
        def changed_capture(*args, **kwargs):
            value = self.capture_original(*args, **kwargs)
            (self.captures["preparation"] / "original/capture/original/empty.log").write_bytes(b"capture boundary mutation")
            return value

        self.original.side_effect = changed_capture
        with patch.object(release, "sign_manifest", wraps=release.sign_manifest) as sign:
            with self.assertRaises(ValueError):
                self.invoke()
            sign.assert_not_called()
        self.assertFalse(self.destination.exists())
        self.original.side_effect = self.capture_original
        copy = release.snapshot_regular_tree
        mutated = []

        def changed_forwarding(source, destination, **arguments):
            copy(source, destination, **arguments)
            if Path(destination).name == "validation-transport" and Path(destination).parent.name == "result":
                carrier = Path(destination).parent / "sdk-apple-validation-evidence"
                record = load_sdk_apple_validation_evidence(carrier)[0]
                (carrier / record["evidenceRoot"] / "apple-validation-attestation.sig").write_bytes(b"late changed signature")
                mutated.append(True)

        with patch.object(release, "snapshot_regular_tree", side_effect=changed_forwarding):
            with self.assertRaises(ValueError):
                self.invoke()
        self.assertEqual([True], mutated)
        self.assertFalse(self.destination.exists())
