"""Core/Android policy is selected before any campaign observation."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ci.sdk_campaign_core_android_election import (
    CORE_ANDROID_INSTANCES, load_core_android_election,
)
from products.inventory import canonical_json_bytes, sha256_bytes


_DIGEST = "sha256:" + "a" * 64
_ROOT = Path(__file__).resolve().parents[2]
_PRODUCER = {"repository": "codex-agent-labs/codex-agent",
             "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40,
             "tree": "b" * 40, "event": "pull_request", "runId": 71,
             "runAttempt": 2, "pullRequest": 31}


def _policy():
    return {"schemaVersion": 1, "family": "core-android", "selections": [
        {"identity": {name: getattr(instance, name)
                      for name in ("product", "component", "phase", "target")},
         "route": "fresh",
         "request": {"producer": dict(_PRODUCER), "expected_build_key": _DIGEST,
                     "expected_product_version": "0.8.0",
                     "trusted_workflow_path": ".github/workflows/product-validation.yml",
                     "trusted_job_name": "product-validation / worker"}}
        for instance in sorted(CORE_ANDROID_INSTANCES)
    ]}


class CoreAndroidElectionTest(TestCase):
    def test_exact_family_is_a_single_immutable_byte_snapshot(self):
        self.assertEqual(18, len(CORE_ANDROID_INSTANCES))
        self.assertEqual(14, sum(i.component == "sdk-core" for i in CORE_ANDROID_INSTANCES))
        self.assertEqual(4, sum(i.component == "sdk-android" for i in CORE_ANDROID_INSTANCES))
        policy = _policy()
        raw = canonical_json_bytes(policy)
        with TemporaryDirectory(dir=_ROOT) as temporary:
            path = Path(temporary) / "election.json"
            path.write_bytes(raw)
            fresh, reused, captured = load_core_android_election(path)
            self.assertEqual(set(fresh), CORE_ANDROID_INSTANCES)
            self.assertEqual({}, reused)
            self.assertEqual(raw, captured)
            path.write_bytes(b"changed after snapshot\n")
            self.assertEqual(raw, captured)
            self.assertEqual("0.8.0", next(iter(fresh.values()))["expected_product_version"])

    def test_same_pr_route_preserves_exact_request_and_converts_key_path(self):
        policy = _policy()
        row = policy["selections"][0]
        row["route"] = "same-pr"
        row["request"] = {
            "expected_build_key": _DIGEST, "expected_product_version": "0.8.0",
            "pull_request": 31, "repository": _PRODUCER["repository"],
            "catalog_artifact_name": "prior-catalog",
            "catalog_public_key": "unselected", "expected_public_key_sha256": _DIGEST,
            "trusted_worker_workflow_path": ".github/workflows/product-validation.yml",
            "trusted_worker_job_name": "product-validation / worker",
            "trusted_catalog_workflow_path": ".github/workflows/product-validation.yml",
            "trusted_catalog_job_name": "product-validation / sdk-catalog",
            "failed_catalog_producer": dict(_PRODUCER),
        }
        with TemporaryDirectory(dir=_ROOT) as temporary:
            key = Path(temporary) / "prior.pub"
            key.write_bytes(b"reviewed public key\n")
            row["request"]["catalog_public_key"] = str(key)
            row["request"]["expected_public_key_sha256"] = sha256_bytes(key.read_bytes())
            path = Path(temporary) / "election.json"
            path.write_bytes(canonical_json_bytes(policy))
            fresh, reused, _ = load_core_android_election(path)
        self.assertEqual(17, len(fresh))
        self.assertEqual(1, len(reused))
        self.assertEqual(key, next(iter(reused.values()))["catalog_public_key"])

    def test_reused_key_and_failed_producer_must_match_independent_pr(self):
        policy = _policy()
        row = policy["selections"][0]
        row["route"] = "same-pr"
        row["request"] = {
            "expected_build_key": _DIGEST, "expected_product_version": "0.8.0",
            "pull_request": 31, "repository": _PRODUCER["repository"],
            "catalog_artifact_name": "prior-catalog",
            "catalog_public_key": "relative.pub", "expected_public_key_sha256": _DIGEST,
            "trusted_worker_workflow_path": ".github/workflows/product-validation.yml",
            "trusted_worker_job_name": "product-validation / worker",
            "trusted_catalog_workflow_path": ".github/workflows/product-validation.yml",
            "trusted_catalog_job_name": "product-validation / sdk-catalog",
            "failed_catalog_producer": dict(_PRODUCER),
        }
        with TemporaryDirectory(dir=_ROOT) as temporary:
            path = Path(temporary) / "election.json"
            key = Path(temporary) / "prior.pub"
            key.write_bytes(b"reviewed public key\n")
            row["request"]["expected_public_key_sha256"] = sha256_bytes(key.read_bytes())
            def rejected():
                path.write_bytes(canonical_json_bytes(policy))
                with self.assertRaises(ValueError):
                    load_core_android_election(path)
            rejected()  # Relative key must not resolve through runner cwd.
            row["request"]["catalog_public_key"] = str(key)
            row["request"]["failed_catalog_producer"]["pullRequest"] = 32
            rejected()
            row["request"]["failed_catalog_producer"]["pullRequest"] = 31
            row["request"]["catalog_public_key"] = str(Path(temporary) / "alias.pub")
            (Path(temporary) / "alias.pub").symlink_to(key)
            rejected()

    def test_partial_duplicate_observation_derived_and_noncanonical_policy_reject(self):
        policy = _policy()
        with TemporaryDirectory(dir=_ROOT) as temporary:
            path = Path(temporary) / "election.json"
            for altered in (
                {**policy, "selections": policy["selections"][:-1]},
                {**policy, "selections": policy["selections"][:-1] +
                 [policy["selections"][0]]},
                {**policy, "selections": list(reversed(policy["selections"]))},
                {**policy, "selections": [{**policy["selections"][0],
                    "request": {**policy["selections"][0]["request"],
                                "observedReceipt": _DIGEST}}] + policy["selections"][1:]},
            ):
                path.write_bytes(canonical_json_bytes(altered))
                with self.assertRaises(ValueError):
                    load_core_android_election(path)
            path.write_bytes(canonical_json_bytes(policy) + b" ")
            with self.assertRaises(ValueError):
                load_core_android_election(path)
