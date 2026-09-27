"""Local protected-input custody fixtures; no hosted SDK admission or signing."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_phase10_protected_inputs as stage
from ci.products.inventory import (
    canonical_json_bytes, public_key_fingerprint, regular_file_inventory,
    sha256_bytes, sha256_file, write_canonical_json,
)
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.signatures import generate_development_key


@unittest.skipUnless(shutil.which("git") and shutil.which("ssh-keygen"),
    "Git and ssh-keygen are required")
class SdkPhase10ProtectedInputsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-protected-inputs-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.checkout = self.root / "original"
        self.checkout.mkdir()
        subprocess.run(["git", "-C", str(self.checkout), "init", "-q"], check=True)
        (self.checkout / "source.txt").write_text("reviewed source\n")
        (self.checkout / "ci/lanes").mkdir(parents=True)
        (self.checkout / "ci/lanes/shared.test.pathspec").write_text("ci/**\n")
        subprocess.run(["git", "-C", str(self.checkout), "add", "source.txt",
            "ci/lanes/shared.test.pathspec"], check=True)
        subprocess.run(["git", "-C", str(self.checkout), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        self.commit = subprocess.check_output(["git", "-C", str(self.checkout),
            "rev-parse", "HEAD"], text=True).strip()
        self.tree = subprocess.check_output(["git", "-C", str(self.checkout),
            "rev-parse", "HEAD^{tree}"], text=True).strip()
        self.trusted = self.root / "trusted"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks",
            str(self.checkout), str(self.trusted)], check=True)
        self.original = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": self.commit,
            "tree": self.tree, "event": "pull_request", "runId": 41,
            "runAttempt": 2, "pullRequest": 31}
        self.authority_producer = {**self.original, "event": "workflow_dispatch",
            "runId": 77, "runAttempt": 1, "pullRequest": None}
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"approved plan\n")
        self.authority_file = self.root / "authority.json"
        self.policies = {}
        election_digests, semantic_digests = {}, {}
        for kind, digests in (("election", election_digests),
                              ("semantic", semantic_digests)):
            for family in stage._FAMILIES:
                path = self.root / f"{kind}-{family}.json"
                write_canonical_json(path, {"family": family, "kind": kind})
                self.policies[(kind, family)] = path
                digests[family] = sha256_file(path)
        write_canonical_json(self.authority_file, {"schemaVersion": 1,
            "product": "sdk", "sdkVersion": "0.8.0",
            "electionSha256": election_digests, "semanticSha256": semantic_digests,
            "artifactPaths": [{"identity": {name: getattr(instance, name)
                for name in ("product", "component", "phase", "target")},
                "relativePath": "outputs/file.bin"}
                for instance in sorted(SDK_CAMPAIGN_INSTANCES)],
            "completedCatalogPin": {"producer": self.original,
                "artifact_name": "catalog", "artifact_id": 5,
                "artifact_sha256": sha256_bytes(b"catalog"),
                "index_sha256": sha256_bytes(b"index"),
                "public_key_sha256": sha256_bytes(b"catalog key"),
                "trusted_workflow_path": ".github/workflows/product-validation.yml",
                "trusted_job_name": "product-validation / sdk-catalog"}})
        _, key, _ = generate_development_key(self.root / "test-key-only")
        self.keys = self.root / "keys"
        self.keys.mkdir()
        (self.keys / "fixture.pub").write_bytes(key.read_bytes())
        self.keyring = self.root / "keyring.json"
        write_canonical_json(self.keyring, {"schemaVersion": 1,
            "algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
            "trustDomain": "release", "activeKey": {"keyId": "fixture",
                "fingerprint": public_key_fingerprint(key.read_bytes())},
            "retiredKeys": []})
        self.keys_digest = sha256_bytes(canonical_json_bytes(
            regular_file_inventory(self.keys)))
        self.control_file = self.root / "control.json"
        self.control = {"schemaVersion": 1, "product": "sdk",
            "trustedSourceCommit": self.commit, "originalProducer": self.original,
            "originalProducerSha256": sha256_bytes(canonical_json_bytes(self.original)),
            "planArtifactId": 6, "planArtifactSha256": sha256_bytes(b"plan zip"),
            "planSha256": sha256_file(self.plan),
            "authorityProducer": self.authority_producer,
            "authorityProducerSha256": sha256_bytes(canonical_json_bytes(
                self.authority_producer)),
            "authorityArtifactId": 7,
            "authorityArtifactSha256": sha256_bytes(b"authority zip"),
            "authorityWorkflowSha": "c" * 40, "trustedWorkflowSha": "d" * 40,
            "stateArtifactId": 8, "stateArtifactSha256": sha256_bytes(b"state"),
            "stateWave": 0, "sdkStateWave": 18,
            "authoritySha256": sha256_file(self.authority_file),
            "keyringSha256": sha256_file(self.keyring),
            "keysInventorySha256": self.keys_digest,
            "replayControlSha256": {name: None for name in stage._REPLAY_CONTROLS}}
        write_canonical_json(self.control_file, self.control)
        self.destination = self.root / "staged"

    def kwargs(self, **changes):
        values = dict(expected_control_sha256=sha256_file(self.control_file),
            trusted_source=self.trusted, trusted_source_commit=self.commit,
            original_checkout=self.checkout, plan_file=self.plan,
            authority_file=self.authority_file,
            expected_authority_sha256=sha256_file(self.authority_file),
            election_files={family: self.policies[("election", family)]
                for family in stage._FAMILIES},
            semantic_files={family: self.policies[("semantic", family)]
                for family in stage._FAMILIES},
            keyring_file=self.keyring, keys_directory=self.keys,
            expected_keyring_sha256=sha256_file(self.keyring),
            expected_keys_inventory_sha256=self.keys_digest,
            destination=self.destination)
        values.update(changes)
        return values

    def invoke(self, **changes):
        with patch.object(stage.products, "_validate_plan", return_value={
                "remoteBuildAuthorized": True, "event": "pull_request"}), \
                patch.object(stage.products, "_consumer",
                    return_value={"producer": self.original}):
            return stage.stage_sdk_phase10_protected_inputs(
                self.control_file, **self.kwargs(**changes))

    def test_exact_approved_inputs_stage_without_observation_or_signing(self):
        with patch.object(stage.products, "_observe_ci_producer_jobs") as observe, \
                patch.object(stage.products, "_download_contract_ci_upload") as download:
            result = self.invoke()
        observe.assert_not_called()
        download.assert_not_called()
        self.assertEqual(str(self.destination), result["destination"])
        self.assertEqual(self.control_file.read_bytes(),
            (self.destination / "control.json").read_bytes())
        self.assertEqual(self.plan.read_bytes(),
            (self.destination / "plan/impact-plan.json").read_bytes())
        self.assertEqual(self.keys_digest, sha256_bytes(canonical_json_bytes(
            regular_file_inventory(self.destination / "keys"))))

    def test_wrong_protected_control_source_checkout_or_plan_rejects(self):
        for changes, message in (
            ({"expected_control_sha256": sha256_bytes(b"wrong")}, "independent protected approval"),
            ({"trusted_source_commit": "e" * 40}, "reviewed commit"),
            ({"expected_authority_sha256": sha256_bytes(b"wrong")}, "independent protected approval"),
            ({"expected_keys_inventory_sha256": sha256_bytes(b"wrong")}, "independent inventory approval"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                self.invoke(**changes)
            self.assertFalse(self.destination.exists())
        self.plan.write_bytes(b"changed plan\n")
        with self.assertRaisesRegex(ValueError, "independently approved digest"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_original_checkout_and_six_policy_bytes_must_match_approved_inputs(self):
        native_policy = self.policies[("semantic", "native")]
        original = native_policy.read_bytes()
        native_policy.write_bytes(b"changed policy\n")
        with self.assertRaisesRegex(ValueError, "approved authority"):
            self.invoke()
        self.assertFalse(self.destination.exists())
        native_policy.write_bytes(original)
        (self.checkout / "later.txt").write_text("new commit\n")
        subprocess.run(["git", "-C", str(self.checkout), "add", "later.txt"], check=True)
        subprocess.run(["git", "-C", str(self.checkout), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "later"], check=True)
        with self.assertRaisesRegex(ValueError, "approved PR commit/tree"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_dirty_or_extra_original_lane_policy_rejects_before_plan_validation(self):
        path = self.checkout / "ci/lanes/shared.test.pathspec"
        path.write_text("tampered/**\n")
        with patch.object(stage.products, "_validate_plan") as validation, \
                self.assertRaisesRegex(ValueError, "lane policy differs"):
            stage.stage_sdk_phase10_protected_inputs(
                self.control_file, **self.kwargs())
        validation.assert_not_called()
        self.assertFalse(self.destination.exists())
        path.write_text("ci/**\n")
        extra = self.checkout / "ci/lanes/untracked.test.pathspec"
        extra.write_text("untracked/**\n")
        with patch.object(stage.products, "_validate_plan") as validation, \
                self.assertRaisesRegex(ValueError, "lane policy differs"):
            stage.stage_sdk_phase10_protected_inputs(
                self.control_file, **self.kwargs())
        validation.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_lane_policy_mutated_during_validation_rejects_without_stage(self):
        policy = self.checkout / "ci/lanes/shared.test.pathspec"

        def mutate(_plan, _root):
            policy.write_text("changed during validation/**\n")
            return {"remoteBuildAuthorized": True, "event": "pull_request"}

        with patch.object(stage.products, "_validate_plan", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "lane policy differs"):
            stage.stage_sdk_phase10_protected_inputs(
                self.control_file, **self.kwargs())
        self.assertFalse(self.destination.exists())

    def test_optional_replay_controls_are_exactly_paired_and_retained(self):
        tooling = self.root / "tooling.json"
        write_canonical_json(tooling, {"kind": "tooling"})
        control = {**self.control, "replayControlSha256": {
            **self.control["replayControlSha256"],
            "sdk_validation_tooling": sha256_file(tooling)}}
        write_canonical_json(self.control_file, control)
        with self.assertRaisesRegex(ValueError, "exact approved file and digest"):
            self.invoke()
        self.assertFalse(self.destination.exists())
        result = self.invoke(replay_control_files={"sdk_validation_tooling": tooling})
        self.assertEqual(tooling.read_bytes(),
            (self.destination / "sdk_validation_tooling.json").read_bytes())
        self.assertEqual(str(self.destination), result["destination"])

    def test_unconfigured_active_signer_fails_closed(self):
        write_canonical_json(self.keyring, {"schemaVersion": 1,
            "algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
            "trustDomain": "release", "activeKey": None, "retiredKeys": []})
        control = {**self.control, "keyringSha256": sha256_file(self.keyring)}
        write_canonical_json(self.control_file, control)
        with self.assertRaisesRegex(ValueError, "No active release"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_authority_mutation_after_snapshot_cannot_publish(self):
        original = stage.snapshot_regular_tree

        def mutate(source, destination):
            original(source, destination)
            self.authority_file.write_bytes(b"changed authority\n")

        with patch.object(stage, "snapshot_regular_tree", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed during staging"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_stage_cli_exposes_fixed_paths_not_an_approval_digest(self):
        arguments = ["stage", "--control", str(self.control_file),
            "--trusted-source", str(self.trusted),
            "--original-checkout", str(self.checkout),
            "--plan", str(self.plan), "--authority", str(self.authority_file),
            "--keyring", str(self.keyring), "--keys-directory", str(self.keys),
            "--destination", str(self.destination),
            "--approved-control-sha256", sha256_file(self.control_file),
            "--trusted-source-commit", self.commit,
            "--approved-authority-sha256", sha256_file(self.authority_file),
            "--approved-keyring-sha256", sha256_file(self.keyring),
            "--approved-keys-inventory-sha256", self.keys_digest]
        for kind in ("election", "semantic"):
            for family in stage._FAMILIES:
                arguments.extend((f"--{kind}-{family}",
                    str(self.policies[(kind, family)])))
        with patch.object(stage.products, "_validate_plan", return_value={
                "remoteBuildAuthorized": True, "event": "pull_request"}), \
                patch.object(stage.products, "_consumer",
                    return_value={"producer": self.original}), \
                redirect_stdout(StringIO()) as output:
            self.assertEqual(0, stage.main(arguments))
        self.assertEqual({"destination": str(self.destination)},
            json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
