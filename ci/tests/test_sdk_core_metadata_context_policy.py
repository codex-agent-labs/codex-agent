"""Core14 caller-policy assembly with mocked official observations only."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_core_metadata_context_policy as policy
from ci.products.inventory import (canonical_json_bytes, load_canonical_json_bytes,
    sha256_bytes, sha256_file, write_canonical_json)
from ci.products.registry import PhaseInstanceId, SDK_FACADE_TARGETS


class CoreContextPolicyTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="core-context-policy-")
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.root = base / "candidate"
        self.root.mkdir()
        self.discovery = self.root / "discovery"
        self.state = self.root / "state"
        self.discovery.mkdir()
        self.state.mkdir()
        self.external = base / "caller"
        self.external.mkdir()
        self.plan = self.root / "plan.json"
        write_canonical_json(self.plan, {"validationCommit": "a" * 40})
        self.producer = {"commit": "a" * 40}
        self.key = "sha256:" + "a" * 64
        self.metadata_receipt = self.root / "metadata-receipt.json"
        self.receipt(self.metadata_receipt, "metadata", "common", self.key)
        self.records = {}
        self.by_instance = {}
        self.sources = {}
        self.source_files = {}
        for number, target in enumerate(SDK_FACADE_TARGETS, 1):
            path = self.root / f"{target}-receipt.json"
            key = f"sha256:{number:064x}"
            self.receipt(path, "validation", target, key)
            request = self.root / f"{target}-request.json"
            write_canonical_json(request, {"target": target})
            self.records[target] = {"validationReceipt": str(path), "facadeRequest": str(request)}
            instance = PhaseInstanceId("sdk", "sdk-core", "validation", target)
            self.by_instance[instance] = {"state": "retained", "buildKey": key,
                "receiptSha256": sha256_bytes(path.read_bytes())}
            self.sources[instance] = path
            self.source_files[path] = sha256_file(path)
            self.source_files[request] = sha256_file(request)
        self.bootstrap = self.external / "bootstrap.json"
        write_canonical_json(self.bootstrap, {"plan": str(self.plan), "toolingTrustDomain": "release",
            "toolingEvidence": str(self.external / "evidence"),
            "toolingPublicKey": str(self.external / "tooling.pub"),
            "javaExecutable": "/usr/bin/java", "toolingKeyring": str(self.external / "keyring.json"),
            "toolingKeysDirectory": str(self.external / "keys"),
            "validations": self.records, "contractDigest": "sha256:" + "b" * 64,
            "componentDigests": {"common": "sha256:" + "c" * 64}})
        self.destination = self.external / "result"
        self.verified = SimpleNamespace(prior_ready_plans={policy._METADATA: {"buildKey": self.key}},
            prior_by_instance=self.by_instance, sources=self.sources, producer=self.producer,
            plan={"validationCommit": "a" * 40})
        self.args = (self.plan, self.discovery, self.state, self.bootstrap,
                     self.metadata_receipt, self.destination)
        self.kwargs = {"expected_build_key": self.key,
            "expected_receipt_sha256": sha256_bytes(self.metadata_receipt.read_bytes()),
            "metadata_artifact_id": 99, "metadata_artifact_sha256": "sha256:" + "d" * 64,
            "original_context": {"repositoryRoot": str(self.root), "metadataRequest": "/original/request"},
            "trusted_workflow_sha": "b" * 40, "repository_root": self.root,
            "environ": {}, "token": "fixture-token"}

    def receipt(self, path, phase, target, key):
        write_canonical_json(path, {"product": "sdk", "component": "sdk-core", "phase": phase,
            "target": target, "buildKey": key, "producer": self.producer})

    def invoke(self, locator=None, **kwargs):
        if locator is None:
            locator = lambda path, **options: {"artifact_id": 99 if Path(path) == self.metadata_receipt else 42,
                                                "artifact_sha256": "sha256:" + "d" * 64}
        with patch.object(policy, "_fresh_policy_sources", return_value=(self.source_files, {})), \
             patch.object(policy.product_reuse, "_verified_product_state", return_value=self.verified), \
             patch.object(policy, "validate_phase_receipt", side_effect=lambda value: value), \
             patch.object(policy, "locate_original_facade_upload", side_effect=locator) as observed:
            result = policy.prepare_original_core_caller_policy(*self.args,
                **{**self.kwargs, **kwargs})
            return result, observed.call_count

    def apple_policy(self):
        apple = self.external / "apple.json"
        files = {name: self.external / f"apple-{name}" for name in
            ("plan", "keyring", "toolingPublicKey", "javaExecutable", "toolingKeyring")}
        trees = {name: self.external / f"apple-{name}" for name in
            ("keysDirectory", "toolingEvidence", "toolingKeysDirectory")}
        for path in files.values():
            path.write_bytes(b"original")
        for path in trees.values():
            path.mkdir()
            (path / "input.txt").write_bytes(b"original")
        write_canonical_json(apple, {**{name: str(path) for name, path in files.items()},
            **{name: str(path) for name, path in trees.items()},
            "attestationPublicKey": None, "attestationTrustDomain": "release",
            "toolingTrustDomain": "release"})
        return apple, files, trees

    def test_all_eleven_selected_originals_and_current_core_upload_publish_once(self):
        result, calls = self.invoke()
        self.assertEqual(12, calls)
        record = load_canonical_json_bytes(result.read_bytes())
        self.assertEqual(set(SDK_FACADE_TARGETS), set(record["validations"]))
        self.assertEqual({"caller-policy.json"}, {path.name for path in self.destination.iterdir()})
        self.assertTrue(all(row["artifactId"] == 42 and "captureRoot" not in row
                            for row in record["validations"].values()))
        self.assertEqual(self.kwargs["expected_receipt_sha256"], record["expectedReceiptSha256"])

    def test_bad_original_upload_or_missing_selected_validation_never_publishes(self):
        with self.assertRaisesRegex(ValueError, "official upload differs"):
            self.invoke(locator=lambda path, **options: {"artifact_id": 98,
                "artifact_sha256": self.kwargs["metadata_artifact_sha256"]})
        self.assertFalse(self.destination.exists())
        self.by_instance.pop(next(iter(self.by_instance)))
        with self.assertRaisesRegex(ValueError, "authenticated wave13 state"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_source_mutation_between_official_calls_never_publishes(self):
        called = 0

        def mutate(path, **options):
            nonlocal called
            called += 1
            if called == 2:
                write_canonical_json(self.plan, {"validationCommit": "b" * 40})
            return {"artifact_id": 99 if called == 1 else 42,
                    "artifact_sha256": self.kwargs["metadata_artifact_sha256"]}

        with self.assertRaisesRegex(ValueError, "changed during observation"):
            self.invoke(locator=mutate)
        self.assertFalse(self.destination.exists())

    def test_optional_apple_policy_bytes_are_pinned_across_observation(self):
        apple, _, _ = self.apple_policy()
        result, calls = self.invoke(sdk_apple_validation_policy_path=apple)
        self.assertEqual(12, calls)
        self.assertTrue(result.is_file())
        self.destination.rename(self.external / "completed-first")
        called = 0

        def mutate(path, **options):
            nonlocal called
            called += 1
            if called == 2:
                write_canonical_json(apple, {"schemaVersion": 2})
            return {"artifact_id": 99 if called == 1 else 42,
                    "artifact_sha256": self.kwargs["metadata_artifact_sha256"]}

        with self.assertRaisesRegex(ValueError, "changed during observation"):
            self.invoke(locator=mutate, sdk_apple_validation_policy_path=apple)
        self.assertFalse(self.destination.exists())

    def test_optional_apple_referenced_tree_mutation_never_publishes(self):
        apple, _, trees = self.apple_policy()
        called = 0

        def mutate(path, **options):
            nonlocal called
            called += 1
            if called == 2:
                (trees["toolingEvidence"] / "input.txt").write_bytes(b"changed")
            return {"artifact_id": 99 if called == 1 else 42,
                    "artifact_sha256": self.kwargs["metadata_artifact_sha256"]}

        with self.assertRaisesRegex(ValueError, "changed during observation"):
            self.invoke(locator=mutate, sdk_apple_validation_policy_path=apple)
        self.assertFalse(self.destination.exists())

    def test_main_parses_canonical_context_and_optional_policy_path(self):
        apple, _, _ = self.apple_policy()
        context = canonical_json_bytes(self.kwargs["original_context"]).decode().strip()
        argv = ["--plan", str(self.plan), "--discovery", str(self.discovery),
            "--state", str(self.state), "--bootstrap-policy", str(self.bootstrap),
            "--metadata-receipt", str(self.metadata_receipt),
            "--destination", str(self.destination), "--expected-build-key", self.key,
            "--expected-receipt-sha256", self.kwargs["expected_receipt_sha256"],
            "--metadata-artifact-id", "99", "--metadata-artifact-sha256",
            self.kwargs["metadata_artifact_sha256"], "--original-context", context,
            "--trusted-workflow-sha", "b" * 40, "--repository-root", str(self.root),
            "--sdk-apple-validation-policy", str(apple)]
        with patch.dict(policy.os.environ, {"GITHUB_TOKEN": "fixture-token"}), \
             patch.object(policy, "prepare_original_core_caller_policy") as prepare:
            self.assertEqual(0, policy.main(argv))
            self.assertEqual(self.kwargs["original_context"], prepare.call_args.kwargs["original_context"])
            self.assertEqual(apple, prepare.call_args.kwargs["sdk_apple_validation_policy_path"])

    def test_signing_secret_rejected_before_state_or_upload_observation(self):
        with self.assertRaisesRegex(ValueError, "signing-secret context"):
            self.invoke(environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "unexpected"})
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
