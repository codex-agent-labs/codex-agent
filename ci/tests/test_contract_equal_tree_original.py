"""Synthetic official API evidence; never a protected-host acceptance claim."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from ci.tests.test_contract_attestation import VERSION, _closure, _payload, _producer, _receipt
from ci.tests.test_contract_release_context import trusted_repository
from ci import contract_equal_tree_original as locator
from products.contract_attestation import build_contract_attestation
from products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree,
)
from products.signatures import generate_development_key


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ContractEqualTreeOriginalTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="contract-equal-tree-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.trusted = self.root / "trusted"
        trusted_repository(self.trusted)
        private, public, signing = generate_development_key(self.root / "signer")
        self.signing = {**signing, "trustDomain": "release"}
        keyring = self.trusted / "gradle/release/product-signing-keys.json"
        keys = self.trusted / "gradle/release/keys"
        keys.mkdir()
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        keyring.write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "namespace": signing["namespace"],
            "algorithm": signing["algorithm"], "trustDomain": "release",
            "activeKey": {"keyId": signing["keyId"], "fingerprint": signing["fingerprint"]},
            "retiredKeys": [],
        }))
        subprocess.run(["git", "add", "--", "gradle/release"], cwd=self.trusted, check=True)
        subprocess.run(["git", "commit", "-qm", "synthetic release key"], cwd=self.trusted, check=True)
        self.source_sha = self.git(self.trusted, "rev-parse", "HEAD")
        self.source_tree = self.git(self.trusted, "rev-parse", "HEAD^{tree}")
        self.candidate = self.root / "candidate"
        subprocess.run(["git", "clone", "-q", "--local", str(self.trusted), str(self.candidate)], check=True)
        self.final = self.git(self.candidate, "rev-parse", "HEAD")
        self.tree = self.git(self.candidate, "rev-parse", "HEAD^{tree}")
        self.tested = subprocess.run(
            ["git", "commit-tree", self.tree, "-p", self.final], cwd=self.candidate,
            input="synthetic equal-tree validation\n", capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.workflow_sha, self.promotion_sha = "c" * 40, "e" * 40
        self.producer = {"repository": locator.REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
                         "event": "merge_group", "commit": self.tested, "tree": self.tree,
                         "pullRequest": None, "runId": 901, "runAttempt": 2}

        payload = self.root / f"codex-agent-contract-{VERSION}.zip"
        _payload(payload)
        receipt = self.root / "receipt.json"
        _receipt(receipt, payload, _producer(7), "development")
        closure = _closure(payload, receipt, self.root / "closure")
        uploaded = self.root / "uploaded"
        build_contract_attestation(payload, receipt, self.signing, private, public,
                                   uploaded / "contract-input", execution_closure=closure,
                                   keyring=keyring, keys_directory=keys, complete_handoff=True)
        policy = uploaded / "caller-policy"
        policy.mkdir()
        (policy / "product-signing-keys.json").write_bytes(keyring.read_bytes())
        snapshot_regular_tree(keys, policy / "keys")
        (uploaded / "caller.json").write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "trustedSourceCommit": self.source_sha,
            "trustedSourceTree": self.source_tree, "trustedWorkflowSha": self.workflow_sha,
            "transportProducer": self.producer, "authorizationReason": "synthetic",
            "event": {}, "environment": {},
        }))
        (uploaded / "original-evidence").mkdir()
        (uploaded / "original-evidence/retained.txt").write_bytes(b"synthetic external original\n")
        self.archive = self.pack()
        self.artifact = {"id": 920, "name": f"codex-agent-contract-release-handoff-{self.tree}",
                         "digest": sha256_bytes(self.archive), "size_in_bytes": len(self.archive),
                         "expired": False, "workflow_run": {"id": 901, "head_sha": self.tested},
                         "created_at": "2026-09-06T10:15:00Z",
                         "archive_download_url": f"https://api.github.com/repos/{locator.REPOSITORY}/actions/artifacts/920/zip"}
        self.run = {"id": 901, "run_attempt": 2, "head_sha": self.tested,
                    "path": ".github/workflows/ci.yml", "event": "merge_group",
                    "status": "completed", "conclusion": "success",
                    "repository": {"full_name": locator.REPOSITORY, "fork": False},
                    "head_repository": {"full_name": locator.REPOSITORY, "fork": False},
                    "referenced_workflows": [{"path": f"{locator.REPOSITORY}/.github/workflows/product-validation.yml@{self.workflow_sha}",
                                              "sha": self.workflow_sha}]}
        self.job = {"id": 910, "name": locator.JOB, "run_id": 901, "head_sha": self.tested,
                    "status": "completed", "conclusion": "success",
                    "started_at": "2026-09-06T10:00:00Z", "completed_at": "2026-09-06T10:30:00Z"}
        self.environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": locator.REPOSITORY,
                            "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": self.final,
                            "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
                            "GITHUB_WORKFLOW_REF": f"{locator.REPOSITORY}/.github/workflows/promote.yml@refs/heads/main",
                            "GITHUB_WORKFLOW_SHA": self.promotion_sha,
                            "GITHUB_RUN_ID": "902", "GITHUB_RUN_ATTEMPT": "1"}
        self.event = {"repository": {"full_name": locator.REPOSITORY},
                      "ref": "refs/heads/main", "after": self.final, "deleted": False}
        self.destination = self.root / "retained-original"

    @staticmethod
    def git(root: Path, *arguments: str) -> str:
        return subprocess.run(["git", *arguments], cwd=root, capture_output=True,
                              text=True, check=True).stdout.strip()

    def pack(self) -> bytes:
        root = self.root / "uploaded"
        packed = io.BytesIO()
        with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as archive:
            for record in reversed(regular_file_inventory(root)):
                path = record["relativePath"]
                archive.writestr(path, (root / path).read_bytes())
        return packed.getvalue()

    def rebind_archive(self) -> None:
        self.archive = self.pack()
        self.artifact["digest"] = sha256_bytes(self.archive)
        self.artifact["size_in_bytes"] = len(self.archive)

    def api(self, url: str, token: str) -> bytes:
        self.assertEqual("synthetic-token", token)
        base = f"https://api.github.com/repos/{locator.REPOSITORY}"
        if url.startswith(base + "/actions/workflows/ci.yml/runs?"):
            value = {"workflow_runs": [self.run]}
        elif url == base + f"/git/commits/{self.tested}":
            value = {"sha": self.tested, "tree": {"sha": self.tree},
                     "parents": [{"sha": self.final}]}
        elif url == base + "/actions/runs/901/attempts/2":
            value = self.run
        elif url.startswith(base + "/actions/runs/901/attempts/2/jobs?"):
            value = {"jobs": [self.job]}
        elif url.startswith(base + "/actions/runs/901/artifacts?"):
            value = {"artifacts": [self.artifact]}
        elif url == base + "/actions/artifacts/920":
            value = self.artifact
        elif url == self.artifact["archive_download_url"]:
            return self.archive
        else:
            raise AssertionError(f"Unexpected HTTP: {url}")
        return json.dumps(value).encode()

    def invoke(self, **changes):
        arguments = dict(trusted_source_sha=self.source_sha,
                         trusted_workflow_sha=self.workflow_sha,
                         trusted_promotion_workflow_sha=self.promotion_sha,
                         final_commit=self.final, event_payload=self.event,
                         environment=self.environment, token="synthetic-token")
        arguments.update(changes)
        with mock.patch("reuse.api_request", side_effect=self.api):
            return locator.capture_equal_tree_contract_original(
                self.trusted, self.candidate, self.destination, **arguments)

    def test_exact_equal_tree_original_retains_signed_handoff_and_public_policy(self) -> None:
        self.assertNotEqual(self.tested, self.final)
        selected = self.invoke()
        self.assertEqual(self.tree, selected["finalTree"])
        self.assertEqual(self.artifact, selected["artifact"])
        self.assertEqual(self.archive, (self.destination / "original-evidence/upload.zip").read_bytes())
        self.assertEqual(regular_file_inventory(self.root / "uploaded"),
                         regular_file_inventory(self.destination / "original-evidence/upload"))
        self.assertEqual(self.signing["keyId"] + ".pub",
                         next((self.destination / "contract-record/policy/keys").iterdir()).name)

    def test_wrong_tree_job_window_policy_and_caller_fail_without_output(self) -> None:
        old_tree = self.tree
        self.tree = "a" * 40
        try:
            with self.assertRaisesRegex(ValueError, "No successful merge-group validation"):
                self.invoke()
            self.assertFalse(self.destination.exists())
        finally:
            self.tree = old_tree
        cases = ((self.job, "conclusion", "failure"),
                 (self.artifact, "created_at", "2026-09-06T11:00:00Z"),
                 (self.artifact, "digest", "sha256:" + "0" * 64))
        for record, field, wrong in cases:
            original = record[field]
            record[field] = wrong
            try:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.invoke()
                self.assertFalse(self.destination.exists())
            finally:
                record[field] = original
        original = self.environment["GITHUB_REF_PROTECTED"]
        self.environment["GITHUB_REF_PROTECTED"] = "false"
        try:
            with self.assertRaisesRegex(ValueError, "protected-main"):
                self.invoke()
        finally:
            self.environment["GITHUB_REF_PROTECTED"] = original
        policy = self.root / "uploaded/caller-policy/product-signing-keys.json"
        policy.write_bytes(b"{}\n")
        # Repack a valid ZIP so the policy mismatch is reached after official
        # upload digest verification rather than failing transport hashing.
        self.rebind_archive()
        with self.assertRaisesRegex(ValueError, "keyring differs"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_officially_digest_bound_but_tampered_signed_handoff_fails(self) -> None:
        signature = self.root / "uploaded/contract-input" / f"codex-agent-contract-{VERSION}.attestation.sig"
        signature.write_bytes(b"not an SSH signature\n")
        self.rebind_archive()
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_cli_passes_independent_pins_and_rejects_non_object_event(self) -> None:
        help_result = subprocess.run(
            [sys.executable, "-B", str(Path(locator.__file__).resolve()), "--help"],
            cwd=self.root, env={key: value for key, value in os.environ.items()
                                if key != "PYTHONPATH"}, capture_output=True, text=True,
        )
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        event = self.root / "event.json"
        event.write_bytes(canonical_json_bytes(self.event))
        arguments = ["--repository-root", str(self.trusted), "--candidate-root", str(self.candidate),
                     "--destination", str(self.destination), "--trusted-source-sha", self.source_sha,
                     "--trusted-workflow-sha", self.workflow_sha,
                     "--trusted-promotion-workflow-sha", self.promotion_sha,
                     "--final-commit", self.final]
        with mock.patch.dict(os.environ, {**self.environment,
                                           "GITHUB_EVENT_PATH": str(event),
                                           "GITHUB_TOKEN": "synthetic-token"}), \
                mock.patch.object(locator, "capture_equal_tree_contract_original") as capture:
            locator.main(arguments)
            capture.assert_called_once_with(
                self.trusted, self.candidate, self.destination,
                trusted_source_sha=self.source_sha, trusted_workflow_sha=self.workflow_sha,
                trusted_promotion_workflow_sha=self.promotion_sha, final_commit=self.final,
                event_payload=self.event, environment=os.environ, token="synthetic-token",
            )
            event.write_bytes(canonical_json_bytes([]))
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                locator.main(arguments)
            capture.assert_called_once()


if __name__ == "__main__":
    unittest.main()
