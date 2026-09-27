"""Independent campaign election pins precede original state observation."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ci.sdk_campaign_catalog_producer import (
    held_sdk_campaign_candidate_from_election,
    held_sdk_campaign_candidate_from_policies,
    held_sdk_campaign_candidate_from_authority,
)
from ci.sdk_campaign_pinned_election import (
    held_pinned_sdk_campaign_election,
    held_pinned_sdk_campaign_semantics,
)
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

    def test_semantic_pins_precede_observation_and_remain_held(self):
        with TemporaryDirectory(dir=_ROOT) as temporary:
            root = Path(temporary)
            elections, election_digests = _files(root)
            policies = {family: root / f"semantic-{family}.json" for family in _FAMILIES}
            raw = canonical_json_bytes({"schemaVersion": 1})
            for path in policies.values():
                path.write_bytes(raw)
            digests = {family: sha256_bytes(raw) for family in policies}
            core = ({}, {}, {}, {}, {}, raw)
            native = ({}, raw)
            apple = ({}, {}, raw)
            with patch("ci.sdk_campaign_pinned_election.load_core_android_semantic_policy",
                    return_value=core), patch(
                    "ci.sdk_campaign_pinned_election.load_native_semantic_policy",
                    return_value=native), patch(
                    "ci.sdk_campaign_pinned_election.load_apple_js_semantic_policy",
                    return_value=apple):
                with held_pinned_sdk_campaign_semantics(policies, digests) as controls:
                    self.assertEqual(8, len(controls))
                with self.assertRaisesRegex(ValueError, "changed during campaign replay"):
                    with held_pinned_sdk_campaign_semantics(policies, digests):
                        policies["native"].write_bytes(b"changed\n")
                policies["native"].write_bytes(raw)
                observed = []

                @contextmanager
                def candidate(_plan, **options):
                    observed.append(set(options["fresh_selections"]))
                    self.assertEqual("observation-token", options["semantic_controls"]
                        ["android_control"]["token"])
                    yield "verified"

                with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate",
                        candidate):
                    with self.assertRaisesRegex(ValueError, "independent digest"):
                        with held_sdk_campaign_candidate_from_policies(Path("plan.json"),
                                election_files=elections,
                                expected_election_sha256=election_digests,
                                semantic_files=policies,
                                expected_semantic_sha256={**digests,
                                    "apple-js": "sha256:" + "0" * 64},
                                token="observation-token", environ={}):
                            self.fail("untrusted policy reached observation")
                    self.assertEqual([], observed)
                    with held_sdk_campaign_candidate_from_policies(Path("plan.json"),
                            election_files=elections,
                            expected_election_sha256=election_digests,
                            semantic_files=policies, expected_semantic_sha256=digests,
                            token="observation-token", environ={}) as value:
                        self.assertEqual("verified", value)
                    self.assertEqual([SDK_CAMPAIGN_INSTANCES], observed)

    def test_real_family_semantic_readers_join_exactly_eight_controls(self):
        from ci.tests.test_sdk_campaign_core_android_semantic_policy import _policy as core_policy
        from ci.tests.test_sdk_campaign_native_semantic_policy import _policy as native_policy
        from ci.tests.test_sdk_campaign_apple_js_semantic_policy import _policy as apple_policy

        with TemporaryDirectory(dir=_ROOT) as temporary:
            root = Path(temporary)
            policies, digests = {}, {}
            for family, source in (("core-android", core_policy),
                                   ("native", native_policy), ("apple-js", apple_policy)):
                path = root / f"{family}.json"
                raw = canonical_json_bytes(source())
                path.write_bytes(raw)
                policies[family], digests[family] = path, sha256_bytes(raw)
            with held_pinned_sdk_campaign_semantics(policies, digests) as controls:
                self.assertEqual(8, len(controls))
                self.assertEqual(4, len(controls["maven_controls"]))
                self.assertEqual("release", controls["javascript_control"]["required_trust_domain"])
                self.assertEqual("development", controls["native_control"]["required_trust_domain"])
                self.assertNotIn("token", controls["android_control"])

    def test_independently_pinned_authority_precedes_all_campaign_observation(self):
        from ci.tests.test_sdk_campaign_core_android_semantic_policy import _policy as core_policy
        from ci.tests.test_sdk_campaign_native_semantic_policy import _policy as native_policy
        from ci.tests.test_sdk_campaign_apple_js_semantic_policy import _policy as apple_policy

        with TemporaryDirectory(dir=_ROOT) as temporary:
            root = Path(temporary)
            elections, election_digests = _files(root)
            semantics, semantic_digests = {}, {}
            for family, source in (("core-android", core_policy),
                                   ("native", native_policy), ("apple-js", apple_policy)):
                path = root / f"semantic-{family}.json"
                raw = canonical_json_bytes(source())
                path.write_bytes(raw)
                semantics[family], semantic_digests[family] = path, sha256_bytes(raw)
            authority = {"schemaVersion": 1, "product": "sdk", "sdkVersion": "0.8.0",
                "electionSha256": election_digests, "semanticSha256": semantic_digests,
                "artifactPaths": [{"identity": {field: getattr(instance, field)
                    for field in ("product", "component", "phase", "target")},
                    "relativePath": "outputs/package.bin"}
                    for instance in sorted(SDK_CAMPAIGN_INSTANCES)],
                "completedCatalogPin": {"producer": dict(_PRODUCER),
                    "artifact_name": "sdk-catalog", "artifact_id": 7,
                    "artifact_sha256": "sha256:" + "a" * 64,
                    "index_sha256": "sha256:" + "b" * 64,
                    "public_key_sha256": "sha256:" + "c" * 64,
                    "trusted_workflow_path": ".github/workflows/product-validation.yml",
                    "trusted_job_name": "product-validation / sdk-catalog"}}
            path = root / "authority.json"
            raw = canonical_json_bytes(authority)
            path.write_bytes(raw)
            observed = []

            @contextmanager
            def candidate(_plan, **options):
                observed.append(options)
                yield "verified"

            with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate", candidate):
                with self.assertRaisesRegex(ValueError, "independent digest"):
                    with held_sdk_campaign_candidate_from_authority(Path("plan.json"),
                            authority_file=path,
                            expected_authority_sha256="sha256:" + "0" * 64,
                            election_files=elections, semantic_files=semantics,
                            token="observation-token", environ={}):
                        self.fail("unapproved authority observed campaign")
                self.assertEqual([], observed)
                with held_sdk_campaign_candidate_from_authority(Path("plan.json"),
                        authority_file=path, expected_authority_sha256=sha256_bytes(raw),
                        election_files=elections, semantic_files=semantics,
                        token="observation-token", environ={}) as result:
                    self.assertEqual("verified", result)
                self.assertEqual(1, len(observed))
                self.assertEqual(SDK_CAMPAIGN_INSTANCES, set(observed[0]["artifact_paths"]))
                self.assertEqual("0.8.0", next(iter(observed[0]["fresh_selections"].values()))
                    ["expected_product_version"])
                observed.clear()
                authority["sdkVersion"] = "0.8.1"
                changed = canonical_json_bytes(authority)
                path.write_bytes(changed)
                with self.assertRaisesRegex(ValueError, "pinned SDK version"):
                    with held_sdk_campaign_candidate_from_authority(Path("plan.json"),
                            authority_file=path,
                            expected_authority_sha256=sha256_bytes(changed),
                            election_files=elections, semantic_files=semantics,
                            token="observation-token", environ={}):
                        self.fail("wrong-version authority observed campaign")
                self.assertEqual([], observed)
