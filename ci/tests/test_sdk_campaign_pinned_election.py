"""Independent campaign election pins precede original state observation."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ci.sdk_campaign_catalog_producer import held_sdk_campaign_candidate_from_election
from ci.sdk_campaign_pinned_election import held_pinned_sdk_campaign_election
from products.inventory import canonical_json_bytes, sha256_bytes
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES


_ROOT = Path(__file__).resolve().parents[2]
_FAMILIES = {
    "core-android": {i for i in SDK_CAMPAIGN_INSTANCES if i.component in {"sdk-core", "sdk-android"}},
    "native": {i for i in SDK_CAMPAIGN_INSTANCES if i.component in {"python", "csharp", "rust", "cpp", "dart"}},
    "apple-js": {i for i in SDK_CAMPAIGN_INSTANCES if i.component in {"sdk-ios", "javascript"}},
}
_PRODUCER = {"repository": "codex-agent-labs/codex-agent",
             "workflowPath": ".github/workflows/product-validation.yml",
             "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
             "runId": 71, "runAttempt": 2, "pullRequest": 31}


def _files(root: Path, *, version="0.8.0"):
    paths, digests = {}, {}
    for family, instances in _FAMILIES.items():
        rows = [{"identity": {name: getattr(instance, name)
                             for name in ("product", "component", "phase", "target")},
                 "route": "fresh", "request": {
                     "producer": dict(_PRODUCER),
                     "expected_build_key": "sha256:" + "c" * 64,
                     "expected_product_version": version,
                     "trusted_workflow_path": ".github/workflows/product-validation.yml",
                     "trusted_job_name": "product-validation / worker"}}
                for instance in sorted(instances)]
        path = root / f"{family}.json"
        raw = canonical_json_bytes({"schemaVersion": 1, "family": family, "selections": rows})
        path.write_bytes(raw)
        paths[family], digests[family] = path, sha256_bytes(raw)
    return paths, digests


class PinnedSdkElectionTest(TestCase):
    def test_exact_61_snapshot_is_held_and_rechecked(self):
        with TemporaryDirectory(dir=_ROOT) as temporary:
            paths, digests = _files(Path(temporary))
            with held_pinned_sdk_campaign_election(paths, digests) as (fresh, reused):
                self.assertEqual(SDK_CAMPAIGN_INSTANCES, set(fresh))
                self.assertEqual({}, reused)
            with self.assertRaisesRegex(ValueError, "changed during campaign"):
                with held_pinned_sdk_campaign_election(paths, digests):
                    paths["native"].write_bytes(b"changed\n")
            paths, digests = _files(Path(temporary))
            with self.assertRaisesRegex(ValueError, "changed during campaign"):
                with held_pinned_sdk_campaign_election(paths, digests) as (fresh, _):
                    next(iter(fresh.values()))["expected_product_version"] = "0.8.1"

    def test_wrong_digest_and_missing_family_fail_before_observation(self):
        with TemporaryDirectory(dir=_ROOT) as temporary:
            paths, digests = _files(Path(temporary))
            with self.assertRaisesRegex(ValueError, "independent digest"):
                with held_pinned_sdk_campaign_election(paths,
                        {**digests, "apple-js": "sha256:" + "0" * 64}):
                    self.fail("untrusted election was yielded")
            with self.assertRaisesRegex(ValueError, "all three"):
                with held_pinned_sdk_campaign_election(
                        {key: value for key, value in paths.items() if key != "native"}, digests):
                    self.fail("partial election was yielded")

            @contextmanager
            def observed_candidate(_plan, **_options):
                self.fail("campaign state was observed before election pinning")
                yield

            with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate", observed_candidate):
                with self.assertRaisesRegex(ValueError, "independent digest"):
                    with held_sdk_campaign_candidate_from_election(Path("plan.json"),
                            policy_files=paths, expected_election_sha256={**digests,
                                "native": "sha256:" + "0" * 64}):
                        self.fail("untrusted campaign observation began")

    def test_wrapper_enters_election_before_candidate(self):
        with TemporaryDirectory(dir=_ROOT) as temporary:
            paths, digests = _files(Path(temporary))
            observed = []

            @contextmanager
            def candidate(_plan, **options):
                observed.append((set(options["fresh_selections"]), set(options["reused_selections"])))
                yield "verified"

            with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate", candidate):
                with held_sdk_campaign_candidate_from_election(Path("plan.json"),
                        policy_files=paths, expected_election_sha256=digests) as value:
                    self.assertEqual("verified", value)
            self.assertEqual([(SDK_CAMPAIGN_INSTANCES, set())], observed)
            with self.assertRaisesRegex(ValueError, "cannot be replaced"):
                with held_sdk_campaign_candidate_from_election(Path("plan.json"),
                        policy_files=paths, expected_election_sha256=digests,
                        fresh_selections={}):
                    self.fail("caller replaced protected election")
