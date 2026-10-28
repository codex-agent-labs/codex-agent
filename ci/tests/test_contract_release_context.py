"""Local caller-context fixtures do not establish protected-host or signing authority."""

from collections.abc import Mapping
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

from ci import contract_release
from ci.products.inventory import canonical_json_bytes, sha256_bytes


REPOSITORY = "codex-agent-labs/codex-agent"
WORKFLOW_SHA = "c" * 40
KEYRING = "gradle/release/product-signing-keys.json"


def trusted_repository(root: Path) -> str:
    """Make only a tiny local Git fixture; tests never execute its source."""
    root.mkdir(parents=True)
    def git(*arguments):
        return subprocess.run(["git", *arguments], cwd=root, check=True,
                              capture_output=True, text=True).stdout.strip()
    git("init", "-q")
    git("config", "user.email", "contract-fixture@example.invalid")
    git("config", "user.name", "Contract fixture")
    version = root / "gradle/release/versions/contract.txt"
    version.parent.mkdir(parents=True)
    version.write_text("0.2.0\n")
    (root / KEYRING).write_bytes(canonical_json_bytes({
        "schemaVersion": 1, "algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
        "trustDomain": "release", "activeKey": None, "retiredKeys": [],
    }))
    git("add", ".")
    git("commit", "-qm", "trusted fixture policy")
    return git("rev-parse", "HEAD")


def contract_context(event="pull_request"):
    producer = {
        "repository": REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
        "commit": "b" * 40, "tree": "d" * 40, "event": event,
        "runId": 71, "runAttempt": 2, "pullRequest": 31 if event == "pull_request" else None,
    }
    if event == "merge_group":
        ref = "refs/heads/gh-readonly-queue/main/pr-31-fixture"
        payload = {"repository": {"full_name": REPOSITORY}, "action": "checks_requested",
                   "merge_group": {"base_sha": "a" * 40, "head_sha": producer["commit"], "head_ref": ref}}
    else:
        ref = "refs/pull/31/merge"
        payload = {
            "repository": {"full_name": REPOSITORY}, "number": 31,
            "action": "labeled", "label": {"name": "ci:remote-final"},
            "pull_request": {
                "number": 31, "draft": False,
                "labels": [{"name": "merge-ready"}, {"name": "ci:full"}, {"name": "ci:remote-final"}],
                "base": {"sha": "a" * 40, "repo": {"full_name": REPOSITORY}},
                "head": {"sha": "f" * 40, "repo": {"full_name": REPOSITORY, "fork": False}},
            },
        }
    environment = {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_EVENT_NAME": event,
        "GITHUB_SHA": producer["commit"], "GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_REF": ref,
    }
    return producer, payload, environment


class SecretReadGuard(Mapping):
    def __init__(self, values):
        self.values = dict(values)
        self.reads = []

    def __getitem__(self, key):
        self.reads.append(key)
        if key in {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", "GITHUB_TOKEN"}:
            raise AssertionError(f"Preflight read protected material: {key}")
        return self.values[key]

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


class ContractReleaseContextTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="contract-release-context-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "trusted"
        self.pin = trusted_repository(self.repository)
        self.producer, self.payload, self.environment = contract_context()

    def invoke(self, *, producer=None, payload=None, environment=None, **changes):
        guard = SecretReadGuard(self.environment if environment is None else environment)
        arguments = {
            "trusted_source_sha": self.pin, "trusted_workflow_sha": WORKFLOW_SHA,
            "artifact_id": 700, "artifact_sha256": sha256_bytes(b"not downloaded"),
            "transport_producer": self.producer if producer is None else producer,
            "contract_version": "0.2.0", "event_payload": self.payload if payload is None else payload,
            "environment": guard, "token": "not-a-real-token",
        }
        arguments.update(changes)
        with mock.patch("reuse.api_request", side_effect=AssertionError("Preflight contacted network")):
            return contract_release.attest_contract_ci(self.repository, self.root / "output", **arguments)

    def test_authorized_pr_and_merge_group_reach_inactive_key_guard_without_secret_or_network(self):
        for event in ("pull_request", "merge_group"):
            with self.subTest(event=event):
                producer, payload, environment = contract_context(event)
                with self.assertRaisesRegex(ValueError, "[Aa]ctive.*key|[Nn]o.*key"):
                    self.invoke(producer=producer, payload=payload, environment=environment, token=None)
                self.assertFalse((self.root / "output").exists())

    def test_missing_malformed_or_wrong_source_and_workflow_pins_fail(self):
        cases = [
            {"trusted_source_sha": value} for value in (None, "", "not-a-sha", "e" * 40)
        ] + [{"trusted_workflow_sha": value} for value in (None, "", "main")]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "[Ss]ource|[Pp]in|SHA|[Ww]orkflow|[Cc]ommit"):
                self.invoke(**changes)

    def test_dirty_tracked_source_is_not_a_pinned_execution_checkout(self):
        version = self.repository / "gradle/release/versions/contract.txt"
        version.write_text("0.2.1\n")
        for staged in (False, True):
            if staged:
                subprocess.run(["git", "add", str(version.relative_to(self.repository))], cwd=self.repository,
                               check=True, capture_output=True)
            with self.subTest(staged=staged), self.assertRaisesRegex(ValueError, "[Cc]lean|[Dd]irty|[Mm]odified|[Cc]hanged"):
                self.invoke()

    def test_context_mismatches_fail_before_public_key_selection(self):
        changes = (
            {"GITHUB_ACTIONS": "false"}, {"GITHUB_REPOSITORY": "unrelated/repository"},
            {"GITHUB_EVENT_NAME": "push"}, {"GITHUB_SHA": "e" * 40},
            {"GITHUB_RUN_ID": "72"}, {"GITHUB_RUN_ATTEMPT": "3"}, {"GITHUB_REF": "refs/heads/main"},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "[Cc]ontext|GitHub|[Pp]roducer|[Rr]ef|[Ee]vent|[Aa]ctions|[Rr]epository|[Rr]un|SHA"):
                self.invoke(environment={**self.environment, **change})

    def test_unapproved_events_do_not_reach_inactive_key_guard(self):
        draft = copy.deepcopy(self.payload)
        draft["pull_request"]["draft"] = True
        full_only = copy.deepcopy(self.payload)
        full_only["label"]["name"] = "ci:full"
        full_only["pull_request"]["labels"] = [{"name": "merge-ready"}, {"name": "ci:full"}]
        fork = copy.deepcopy(self.payload)
        fork["pull_request"]["head"]["repo"]["fork"] = True
        synchronized = copy.deepcopy(self.payload)
        synchronized["action"] = "synchronize"
        synchronized.pop("label")
        for payload in (draft, full_only, fork, synchronized):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, "[Aa]uthor|[Aa]pprov|[Dd]raft|[Ff]inal|[Tt]rust|[Ee]vent"):
                self.invoke(payload=payload)
        with self.assertRaisesRegex(ValueError, "[Ss]upport|[Ee]vent|[Dd]ispatch"):
            self.invoke(producer={**self.producer, "event": "workflow_dispatch", "pullRequest": None},
                        environment={**self.environment, "GITHUB_EVENT_NAME": "workflow_dispatch"})


if __name__ == "__main__":
    unittest.main()
