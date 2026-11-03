import tempfile
import unittest
from pathlib import Path

from ci.sdk_apple_js_campaign_election import APPLE_JS_INSTANCES, load_family_election
from products.inventory import canonical_json_bytes, sha256_bytes


def _policy():
    return {"schemaVersion": 1, "family": "apple-js", "selections": [{
        "identity": {field: getattr(instance, field)
            for field in ("product", "component", "phase", "target")},
        "route": "fresh",
        "request": {
            "producer": {
                "repository": "codex-agent-labs/codex-agent",
                "workflowPath": ".github/workflows/product-validation.yml",
                "commit": "a" * 40, "tree": "b" * 40,
                "event": "pull_request", "runId": 1, "runAttempt": 1,
                "pullRequest": 31,
            }, "expected_build_key": "sha256:" + "a" * 64,
            "expected_product_version": "0.8.0",
            "trusted_workflow_path": ".github/workflows/product-validation.yml",
            "trusted_job_name": "original-worker",
        },
    } for instance in sorted(APPLE_JS_INSTANCES)]}


def _reused_request(directory):
    key = Path(directory).resolve() / "catalog.pub"
    key.write_bytes(b"test catalog public key\n")
    return {
        "expected_build_key": "sha256:" + "a" * 64,
        "expected_product_version": "0.8.0",
        "pull_request": 31, "repository": "codex-agent-labs/codex-agent",
        "catalog_artifact_name": "catalog", "catalog_public_key": key.as_posix(),
        "expected_public_key_sha256": sha256_bytes(key.read_bytes()),
        "trusted_worker_workflow_path": ".github/workflows/product-validation.yml",
        "trusted_worker_job_name": "worker",
        "trusted_catalog_workflow_path": ".github/workflows/product-validation.yml",
        "trusted_catalog_job_name": "catalog",
    }


class AppleJsElectionTest(unittest.TestCase):
    def test_exact_family_is_loaded_from_canonical_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "election.json"
            raw = canonical_json_bytes(_policy())
            path.write_bytes(raw)
            fresh, reused, selected = load_family_election(path)
            self.assertEqual(set(fresh), APPLE_JS_INSTANCES)
            self.assertEqual(reused, {})
            self.assertEqual(selected, raw)

    def test_missing_duplicate_unsorted_and_foreign_phase_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "election.json"
            for mutation in ("missing", "duplicate", "unsorted", "foreign"):
                policy = _policy()
                rows = policy["selections"]
                if mutation == "missing":
                    rows.pop()
                elif mutation == "duplicate":
                    rows[-1] = rows[0]
                elif mutation == "unsorted":
                    rows[0], rows[1] = rows[1], rows[0]
                else:
                    rows[-1]["identity"]["component"] = "sdk-android"
                with self.subTest(mutation=mutation):
                    path.write_bytes(canonical_json_bytes(policy))
                    with self.assertRaises(ValueError):
                        load_family_election(path)

    def test_reused_route_converts_only_catalog_key_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "election.json"
            policy = _policy()
            row = policy["selections"][0]
            row["route"] = "same-pr"
            row["request"] = _reused_request(directory)
            path.write_bytes(canonical_json_bytes(policy))
            fresh, reused, _ = load_family_election(path)
            self.assertNotIn(next(iter(reused)), fresh)
            self.assertEqual(next(iter(reused.values()))["catalog_public_key"],
                Path(directory).resolve() / "catalog.pub")

    def test_unknown_fields_and_noncanonical_bytes_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "election.json"
            policy = _policy()
            policy["selections"][0]["request"]["extra"] = True
            path.write_bytes(canonical_json_bytes(policy))
            with self.assertRaises(ValueError):
                load_family_election(path)
            path.write_bytes(canonical_json_bytes(_policy()) + b"\n")
            with self.assertRaises(ValueError):
                load_family_election(path)

    def test_bad_producer_and_digest_fail_before_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "election.json"
            for mutation in ("producer", "digest"):
                policy = _policy()
                request = policy["selections"][0]["request"]
                if mutation == "producer":
                    request["producer"]["runId"] = None
                else:
                    request["expected_build_key"] = "sha256:wrong"
                with self.subTest(mutation=mutation):
                    path.write_bytes(canonical_json_bytes(policy))
                    with self.assertRaises(ValueError):
                        load_family_election(path)

    def test_bad_route_workflow_and_catalog_key_fail_before_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "election.json"
            reused = _reused_request(directory)
            for mutation in ("route", "workflow", "relative-key", "unnormalized-key"):
                policy = _policy()
                row = policy["selections"][0]
                if mutation == "route":
                    row["route"] = "system"
                elif mutation == "workflow":
                    row["request"]["trusted_workflow_path"] = "../worker.yml"
                else:
                    row["route"] = "same-pr"
                    row["request"] = dict(reused)
                    row["request"]["catalog_public_key"] = (
                        "tmp/catalog.pub" if mutation == "relative-key" else "/tmp/../catalog.pub")
                with self.subTest(mutation=mutation):
                    path.write_bytes(canonical_json_bytes(policy))
                    with self.assertRaises(ValueError):
                        load_family_election(path)

    def test_reused_key_bytes_and_failed_producer_are_bound_before_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "election.json"
            for mutation in ("key-bytes", "key-symlink", "failed-pr", "failed-repository", "failed-event"):
                policy = _policy()
                row = policy["selections"][0]
                row["route"] = "same-pr"
                row["request"] = _reused_request(directory)
                request = row["request"]
                if mutation == "key-bytes":
                    Path(request["catalog_public_key"]).write_bytes(b"tampered\n")
                elif mutation == "key-symlink":
                    key = Path(request["catalog_public_key"])
                    target = key.with_name("actual-catalog.pub")
                    key.rename(target)
                    key.symlink_to(target)
                else:
                    producer = dict(_policy()["selections"][0]["request"]["producer"])
                    if mutation == "failed-pr":
                        producer["pullRequest"] = 32
                    elif mutation == "failed-repository":
                        producer["repository"] = "other/project"
                    else:
                        producer["event"] = "workflow_dispatch"
                        producer["pullRequest"] = None
                    request["failed_catalog_producer"] = producer
                with self.subTest(mutation=mutation):
                    path.write_bytes(canonical_json_bytes(policy))
                    with self.assertRaises(ValueError):
                        load_family_election(path)
                key = Path(directory).resolve() / "catalog.pub"
                if key.is_symlink():
                    key.unlink()

    def test_custody_failed_producer_must_match_selected_pr(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "election.json"
            policy = _policy()
            row = policy["selections"][0]
            row["route"] = "same-pr"
            selected = _reused_request(directory)
            row["request"] = {field: selected[field] for field in (
                "expected_build_key", "expected_product_version", "pull_request",
                "repository", "trusted_worker_workflow_path", "trusted_worker_job_name")}
            row["request"]["custody_ref"] = "failed-attempt"
            row["request"]["failed_catalog_producer"] = {
                **_policy()["selections"][0]["request"]["producer"],
                "pullRequest": 32,
            }
            path.write_bytes(canonical_json_bytes(policy))
            with self.assertRaises(ValueError):
                load_family_election(path)

    def test_symlink_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "election.json"
            target.write_bytes(canonical_json_bytes(_policy()))
            link = root / "linked-election.json"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                load_family_election(link)


if __name__ == "__main__":
    unittest.main()
