"""Non-secret Core context preparation after full original replay.

The original reader fixture mocks hosted observation and native execution; no
real hosted, compiler, or protected-environment acceptance is claimed.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_core_metadata_context_preparation as preparation
from ci.tests import test_sdk_facade_metadata_original as original_fixture
from ci.products.inventory import (canonical_json_bytes, load_canonical_json_bytes,
    sha256_bytes, write_canonical_json)
from ci.products.signatures import generate_development_key


class OriginalCoreContextPreparationTest(unittest.TestCase):
    def setUp(self):
        external = tempfile.TemporaryDirectory(prefix="core-context-preparation-")
        self.addCleanup(external.cleanup)
        self.external = Path(external.name).resolve()
        _, public, development = generate_development_key(self.external / "ephemeral")
        self.keys = self.external / "keys"
        self.keys.mkdir()
        self.signing = {**development, "trustDomain": "release", "keyId": "fixture-release"}
        (self.keys / "fixture-release.pub").write_bytes(public.read_bytes())
        self.keyring = self.external / "keyring.json"
        write_canonical_json(self.keyring, {"schemaVersion": 1,
            "namespace": self.signing["namespace"], "algorithm": self.signing["algorithm"],
            "trustDomain": "release", "activeKey": {"keyId": "fixture-release",
            "fingerprint": self.signing["fingerprint"]}, "retiredKeys": []})
        fixture = original_fixture.FacadeMetadataOriginalTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.artifact_sha = "sha256:" + "d" * 64
        original_capture = fixture.capture.side_effect

        def capture(*args, **kwargs):
            value = original_capture(*args, **kwargs)
            value["artifact"]["digest"] = self.artifact_sha
            (args[1] / "capture-transport.json").write_bytes(canonical_json_bytes(value))
            return value

        fixture.capture.side_effect = capture
        self.destination = self.external / "prepared-context"

    def arguments(self):
        f = self.fixture
        arguments = f.f.arguments()
        for name in ("discovery", "state", "destination", "expected_build_key"):
            arguments.pop(name)
        return {**arguments, "metadata_receipt_path": f.receipt_path,
            "destination": self.destination, "expected_build_key": f.receipt["buildKey"],
            "expected_receipt_sha256": sha256_bytes(f.receipt_path.read_bytes()),
            "artifact_id": 123, "artifact_sha256": self.artifact_sha,
            "original_context": f.context, "signing_keyring": self.keyring,
            "signing_keys_directory": self.keys,
            "tooling_keyring": None, "tooling_keys_directory": None}

    def caller_policy(self):
        args = self.arguments()
        value = {"schemaVersion": 1, "plan": str(args["plan"]),
            "metadataReceiptPath": str(args["metadata_receipt_path"]),
            "expectedBuildKey": args["expected_build_key"],
            "expectedReceiptSha256": args["expected_receipt_sha256"],
            "artifactId": args["artifact_id"], "artifactSha256": args["artifact_sha256"],
            "originalContext": args["original_context"],
            "validations": {target: {name: str(item) if isinstance(item, Path) else item
                for name, item in record.items()} for target, record in args["validations"].items()},
            "contractDigest": args["contract_digest"],
            "componentDigests": args["component_digests"],
            "toolingEvidence": str(args["tooling_evidence"]),
            "toolingPublicKey": str(args["tooling_public_key"]),
            "javaExecutable": str(args["java_executable"]),
            "policyRevision": args["policy_revision"],
            "requiredTrustDomain": args["required_trust_domain"],
            "toolingKeyring": args["tooling_keyring"],
            "toolingKeysDirectory": args["tooling_keys_directory"]}
        path = self.external / "independent-caller.json"
        write_canonical_json(path, value)
        return path, value

    def caller_arguments(self, caller_policy):
        return {"caller_policy": caller_policy, "destination": self.destination,
            "repository_root": self.arguments()["repository_root"],
            "trusted_workflow_sha": self.arguments()["trusted_workflow_sha"],
            "signing_keyring": self.keyring, "signing_keys_directory": self.keys,
            "environ": self.arguments()["environ"], "token": self.arguments()["token"]}

    def test_prepares_unsigned_exact_record_only_after_full_original_reader(self):
        args = self.arguments()
        manifest = preparation.prepare_original_core_context(**args)
        self.fixture.capture.assert_called_once()
        self.assertEqual({"original-context.json"}, {path.name for path in self.destination.iterdir()})
        self.assertEqual({"schemaVersion": 1, "kind": "sdk-core-metadata-original-context",
            "buildKey": self.fixture.receipt["buildKey"],
            "receiptSha256": args["expected_receipt_sha256"],
            "artifactId": 123, "artifactSha256": self.artifact_sha,
            "producer": self.fixture.receipt["producer"],
            "originalContext": self.fixture.context, "signing": self.signing},
            load_canonical_json_bytes(manifest.read_bytes()))

    def test_wrong_selection_or_original_worker_never_publishes(self):
        for field, value in (("expected_build_key", "sha256:" + "e" * 64),
                             ("artifact_sha256", "sha256:" + "e" * 64),
                             ("original_context", {**self.fixture.context,
                                                   "metadataRequest": "/wrong/request"})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                preparation.prepare_original_core_context(**{**self.arguments(), field: value})
            self.assertFalse(self.destination.exists())

    def test_reader_exit_failure_cannot_leave_candidate_evidence(self):
        self.fixture.f.f.exit_failure = "jvm"
        with self.assertRaisesRegex(ValueError, "reader exit rejected"):
            preparation.prepare_original_core_context(**self.arguments())
        self.assertFalse(self.destination.exists())

    def test_missing_active_key_and_output_overlap_reject_before_observation(self):
        write_canonical_json(self.keyring, {"schemaVersion": 1,
            "namespace": self.signing["namespace"], "algorithm": self.signing["algorithm"],
            "trustDomain": "release", "activeKey": None, "retiredKeys": []})
        with self.assertRaisesRegex(ValueError, "No active release"):
            preparation.prepare_original_core_context(**self.arguments())
        with self.assertRaisesRegex(ValueError, "overlaps an original input"):
            preparation.prepare_original_core_context(**{**self.arguments(),
                "destination": self.fixture.root / "prepared-context"})
        self.fixture.capture.assert_not_called()

    def test_signing_secret_rejected_before_original_observation(self):
        with self.assertRaisesRegex(ValueError, "signing-secret context"):
            preparation.prepare_original_core_context(**{**self.arguments(),
                "environ": {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "unexpected"}})
        self.fixture.capture.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_cli_entry_consumes_external_canonical_caller_policy(self):
        path, _ = self.caller_policy()
        manifest = preparation.prepare_from_caller_policy(**self.caller_arguments(path))
        self.fixture.capture.assert_called_once()
        self.assertEqual({"original-context.json"}, {entry.name for entry in self.destination.iterdir()})
        self.assertEqual(self.fixture.context,
                         load_canonical_json_bytes(manifest.read_bytes())["originalContext"])

    def test_module_main_routes_only_explicit_caller_inputs(self):
        path, _ = self.caller_policy()
        args = ["--caller-policy", str(path), "--destination", str(self.destination),
            "--repository-root", str(self.arguments()["repository_root"]),
            "--trusted-workflow-sha", self.arguments()["trusted_workflow_sha"],
            "--signing-keyring", str(self.keyring), "--signing-keys-directory", str(self.keys)]
        with patch.dict(preparation.os.environ, {"GITHUB_TOKEN": self.arguments()["token"]}):
            self.assertEqual(0, preparation.main(args))
        self.fixture.capture.assert_called_once()
        self.assertTrue((self.destination / "original-context.json").is_file())

    def test_caller_policy_secret_or_retained_validation_rejects_before_observation(self):
        path, policy = self.caller_policy()
        args = self.caller_arguments(path)
        with self.assertRaisesRegex(ValueError, "signing-secret context"):
            preparation.prepare_from_caller_policy(**{**args,
                "environ": {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "unexpected"}})
        retained = policy["validations"][next(iter(policy["validations"]))]
        retained.pop("artifactId")
        retained.pop("artifactSha256")
        retained["captureRoot"] = str(self.external)
        write_canonical_json(path, policy)
        with self.assertRaises(ValueError):
            preparation.prepare_from_caller_policy(**args)
        self.fixture.capture.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_caller_policy_mutation_after_reader_never_publishes(self):
        path, policy = self.caller_policy()
        reader = preparation.prepare_original_core_context

        def mutate(*args, **kwargs):
            result = reader(*args, **kwargs)
            write_canonical_json(path, {**policy, "artifactId": 124})
            return result

        with patch.object(preparation, "prepare_original_core_context", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "caller policy changed"):
                preparation.prepare_from_caller_policy(**self.caller_arguments(path))
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
