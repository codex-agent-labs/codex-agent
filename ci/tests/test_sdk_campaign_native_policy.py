"""The native election is exact and independent of campaign observations."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ci.sdk_campaign_native_policy import load_native_election
from products.inventory import canonical_json_bytes, sha256_bytes
from products.sdk_campaign_native import NATIVE_CAMPAIGN_INSTANCES


_DIGEST = "sha256:" + "a" * 64
_PRODUCER = {"repository": "codex-agent-labs/codex-agent",
    "workflowPath": ".github/workflows/sdk-validation.yml",
    "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
    "runId": 1, "runAttempt": 1, "pullRequest": 31}


def _policy():
    return {"schemaVersion": 1, "family": "native", "selections": [
        {"identity": {field: getattr(instance, field) for field in
            ("product", "component", "phase", "target")},
         "route": "fresh", "request": {"producer": deepcopy(_PRODUCER),
            "expected_build_key": _DIGEST, "expected_product_version": "0.8.0",
            "trusted_workflow_path": ".github/workflows/sdk-validation.yml",
            "trusted_job_name": "sdk-native-worker"}}
        for instance in sorted(NATIVE_CAMPAIGN_INSTANCES)]}


class NativeElectionTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "election.json"

    def load(self, policy):
        self.path.write_bytes(canonical_json_bytes(policy))
        return load_native_election(self.path)

    def test_exact_35_and_original_bytes(self):
        policy = _policy()
        fresh, reused, raw = self.load(policy)
        self.assertEqual(set(fresh), NATIVE_CAMPAIGN_INSTANCES)
        self.assertEqual(len(fresh), 35)
        self.assertEqual(reused, {})
        self.assertEqual(raw, canonical_json_bytes(policy))

    def test_reused_catalog_key_becomes_path(self):
        policy = _policy()
        key = Path(self.temporary.name) / "catalog.pub"
        key.write_bytes(b"test-catalog-public-key\n")
        policy["selections"][0]["route"] = "same-pr"
        policy["selections"][0]["request"] = {
            "expected_build_key": _DIGEST, "expected_product_version": "0.8.0",
            "pull_request": 31, "repository": "codex-agent-labs/codex-agent",
            "catalog_artifact_name": "catalog", "catalog_public_key": str(key),
            "expected_public_key_sha256": sha256_bytes(key.read_bytes()),
            "trusted_worker_workflow_path": ".github/workflows/sdk-validation.yml",
            "trusted_worker_job_name": "sdk-native-worker",
            "trusted_catalog_workflow_path": ".github/workflows/sdk-failed-catalog.yml",
            "trusted_catalog_job_name": "catalog"}
        fresh, reused, _ = self.load(policy)
        self.assertEqual(len(fresh), 34)
        self.assertEqual(len(reused), 1)
        self.assertEqual(next(iter(reused.values()))["catalog_public_key"], key)
        policy["selections"][0]["request"]["catalog_public_key"] = "relative.pub"
        with self.assertRaises(ValueError):
            self.load(policy)
        policy["selections"][0]["request"]["catalog_public_key"] = str(key) + "/../catalog.pub"
        with self.assertRaises(ValueError):
            self.load(policy)
        policy["selections"][0]["request"]["catalog_public_key"] = str(key)
        policy["selections"][0]["request"]["expected_public_key_sha256"] = _DIGEST
        with self.assertRaises(ValueError):
            self.load(policy)
        policy["selections"][0]["request"]["expected_public_key_sha256"] = sha256_bytes(key.read_bytes())
        shortcut = Path(self.temporary.name) / "key-directory-link"
        shortcut.symlink_to(key.parent, target_is_directory=True)
        policy["selections"][0]["request"]["catalog_public_key"] = str(shortcut / key.name)
        with self.assertRaises(ValueError):
            self.load(policy)

    def test_symlinked_policy_or_catalog_key_parent_fails(self):
        policy = _policy()
        self.path.write_bytes(canonical_json_bytes(policy))
        shortcut = Path(self.temporary.name) / "shortcut"
        shortcut.symlink_to(self.path.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            load_native_election(shortcut / self.path.name)

    def test_invalid_workflow_or_job_fails_before_lookup(self):
        for field, bad in (("trusted_workflow_path", "../outside.yml"),
                           ("trusted_workflow_path", ".github/workflows/nested/job.yml"),
                           ("trusted_job_name", "worker\nname")):
            with self.subTest(field=field, bad=bad):
                policy = _policy()
                policy["selections"][0]["request"][field] = bad
                with self.assertRaises(ValueError):
                    self.load(policy)

    def test_custody_route_preserves_caller_owned_producer_and_ref(self):
        policy = _policy()
        policy["selections"][0]["route"] = "same-pr"
        policy["selections"][0]["request"] = {
            "expected_build_key": _DIGEST, "expected_product_version": "0.8.0",
            "pull_request": 31, "repository": "codex-agent-labs/codex-agent",
            "trusted_worker_workflow_path": ".github/workflows/sdk-validation.yml",
            "trusted_worker_job_name": "sdk-native-worker",
            "failed_catalog_producer": deepcopy(_PRODUCER), "custody_ref": "prior-failure"}
        _, reused, _ = self.load(policy)
        self.assertEqual(next(iter(reused.values()))["failed_catalog_producer"], _PRODUCER)
        policy["selections"][0]["request"]["custody_ref"] = ""
        with self.assertRaises(ValueError):
            self.load(policy)
        policy["selections"][0]["request"]["custody_ref"] = "prior-failure"
        for changes in ({"pullRequest": 32},
                        {"repository": "other-owner/other-repo"},
                        {"event": "workflow_dispatch", "pullRequest": None}):
            with self.subTest(changes=changes):
                producer = policy["selections"][0]["request"]["failed_catalog_producer"]
                original = {field: producer[field] for field in changes}
                producer.update(changes)
                with self.assertRaises(ValueError):
                    self.load(policy)
                producer.update(original)

    def test_wrong_or_reordered_phase_and_extra_request_fail(self):
        for mutation in ("missing", "duplicate", "reordered", "extra"):
            with self.subTest(mutation=mutation):
                policy = _policy()
                rows = policy["selections"]
                if mutation == "missing":
                    rows.pop()
                elif mutation == "duplicate":
                    rows[1] = deepcopy(rows[0])
                elif mutation == "reordered":
                    rows[0], rows[1] = rows[1], rows[0]
                else:
                    rows[0]["request"]["observedBuildKey"] = _DIGEST
                with self.assertRaises(ValueError):
                    self.load(policy)

    def test_identity_and_schema_types_are_exact(self):
        policy = _policy()
        policy["schemaVersion"] = True
        with self.assertRaises(ValueError):
            self.load(policy)
        policy = _policy()
        policy["selections"][0]["identity"]["component"] = []
        with self.assertRaises(ValueError):
            self.load(policy)

    def test_noncanonical_and_wrong_family_fail(self):
        self.path.write_bytes(b'{"schemaVersion":1,"family":"native","selections":[]}\n')
        with self.assertRaises(ValueError):
            load_native_election(self.path)
        policy = _policy()
        policy["family"] = "javascript"
        with self.assertRaises(ValueError):
            self.load(policy)
        self.path.write_bytes(canonical_json_bytes(_policy()) + b"\n")
        with self.assertRaises(ValueError):
            load_native_election(self.path)
