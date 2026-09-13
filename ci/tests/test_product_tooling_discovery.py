"""Product/tooling discovery routing checks; cryptographic admission is tested separately."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import product_reuse  # noqa: E402
import tooling_discovery  # noqa: E402
from products.inventory import canonical_json_bytes, sha256_bytes  # noqa: E402
from products.registry import PhaseInstanceId  # noqa: E402
from ci.tests.test_product_reuse_adapter import VERSIONS, impact_plan  # noqa: E402


WORKFLOW_PIN = "c" * 40


class ProductToolingDiscoveryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="product-tooling-discovery-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan_path = self.root / "impact-plan.json"
        self.output = self.root / "github-output"
        self.java = self.root / "java"
        self.java.write_bytes(b"caller Java\n")

    def run_discovery(self, instance, *, catalogs=(), report=None, explicit=(),
                      plan=None, destination_name="reuse", environment=None,
                      sdk_validation_tooling=None, automatic=True,
                      capture_side_effect=None):
        plan = impact_plan(changed=["known.kt"]) if plan is None else plan
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        destination = self.root / destination_name
        events = []

        def catalog_lookup(*_args, **kwargs):
            events.append("catalogs")
            runs = kwargs.get("tooling_candidate_runs")
            if runs is not None:
                runs.extend((41, 39))
            return list(catalogs)

        def discover(destination, repository, **kwargs):
            events.append("tooling")
            self.assertEqual(self.root, repository)
            self.assertNotEqual(self.root, destination)
            self.assertNotIn(self.root, destination.parents)
            self.assertEqual([41, 39], kwargs["candidate_run_ids"])
            self.assertEqual(WORKFLOW_PIN, kwargs["trusted_workflow_sha"])
            self.assertEqual(plan["validationCommit"], kwargs["policy_revision"])
            self.assertEqual(self.java, kwargs["java_executable"])
            selected = report
            if report["toolingPolicy"] is not None:
                capture = destination / "capture"
                evidence = capture / "evidence"
                keys = capture / "policy/keys"
                evidence.mkdir(parents=True)
                keys.mkdir(parents=True)
                (evidence / "tooling-evidence.json").write_bytes(b"verified evidence\n")
                (keys / "release.pub").write_bytes(b"public key\n")
                (capture / "policy/product-signing-keys.json").write_bytes(b"{}\n")
                policy = {
                    "evidence": str(evidence),
                    "publicKey": str(keys / "release.pub"),
                    "javaExecutable": str(self.java),
                    "requiredTrustDomain": "release",
                    "keyring": str(capture / "policy/product-signing-keys.json"),
                    "keysDirectory": str(keys),
                }
                selected = {**report, "toolingPolicy": policy}
                (capture / "tooling-policy.json").write_bytes(canonical_json_bytes(policy))
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "discovery.json").write_bytes(canonical_json_bytes(selected))
            return selected

        def capture(roots, _destination, _artifact_root, **kwargs):
            events.append("capture")
            if capture_side_effect is not None:
                return capture_side_effect(roots, kwargs)
            return []

        closure = (instance,)
        with mock.patch.object(product_reuse, "_validate_plan", return_value=plan), \
                mock.patch.object(product_reuse, "_requested", return_value=closure), \
                mock.patch.object(product_reuse, "_dependency_closure", return_value=closure), \
                mock.patch.object(product_reuse, "sdk_runtime_source", return_value=None), \
                mock.patch.object(product_reuse, "_versions", return_value=VERSIONS), \
                mock.patch.object(product_reuse, "_release_trust", return_value=object()), \
                mock.patch.object(product_reuse, "_discover_catalogs", side_effect=catalog_lookup), \
                mock.patch.object(product_reuse, "_capture_native_handoffs", return_value=[]), \
                mock.patch.object(product_reuse, "_capture_sdk_handoffs", side_effect=capture), \
                mock.patch.object(product_reuse, "_capture_aggregate_handoffs", return_value=[]), \
                mock.patch.object(product_reuse, "_authorities", return_value=(None, "stop-after-tooling")), \
                mock.patch.object(tooling_discovery, "discover_tooling_ci", side_effect=discover) as tooling:
            result = product_reuse.discover(
                self.plan_path, destination, self.output, repository_root=self.root,
                environ={"GITHUB_TOKEN": "token"} if environment is None else environment,
                sdk_evidence_roots=tuple(explicit), sdk_validation_tooling=sdk_validation_tooling,
                tooling_java_executable=self.java if automatic else None,
                tooling_workflow_sha=WORKFLOW_PIN if automatic else None,
            )
        return result, destination, events, tooling

    @staticmethod
    def catalog(root: Path):
        return product_reuse.Catalog(
            source="same-pr", index={}, index_sha256=sha256_bytes(b"index"),
            request={}, objects={}, sdk_validation_evidence_root=root,
        )

    def outputs(self):
        return dict(line.split("=", 1) for line in self.output.read_text().splitlines())

    def test_authenticated_tooling_policy_is_forwarded_before_catalog_carrier_admission(self):
        instance = PhaseInstanceId("sdk", "csharp", "validation", "linux-x64")
        catalog_root = self.root / "catalog-sdk"
        producer = {"repository": "fixture/repository", "tree": "d" * 40}
        report = {
            "schemaVersion": 1,
            "selected": {"artifactId": 71, "artifactSha256": "sha256:" + "e" * 64,
                         "transportProducer": producer},
            "attempts": [],
            "toolingPolicy": {"selected": True},
        }

        def capture(roots, kwargs):
            self.assertEqual((catalog_root,), roots)
            policy = kwargs["tooling"]
            retained = self.root / "reuse/tooling-discovery/capture"
            self.assertEqual(str(retained / "evidence"), policy["evidence"])
            self.assertEqual(str(retained / "policy/keys/release.pub"), policy["publicKey"])
            self.assertEqual(str(retained / "policy/product-signing-keys.json"), policy["keyring"])
            self.assertEqual(str(retained / "policy/keys"), policy["keysDirectory"])
            self.assertEqual(str(self.java), policy["javaExecutable"])
            self.assertTrue((retained / "evidence/tooling-evidence.json").is_file())
            return [{"receiptSha256": "sha256:" + "f" * 64}]

        result, destination, events, tooling = self.run_discovery(
            instance, catalogs=(self.catalog(catalog_root),), report=report,
            capture_side_effect=capture,
        )
        self.assertEqual("stop-after-tooling", result["reason"])
        self.assertEqual(["catalogs", "tooling", "capture"], events)
        tooling.assert_called_once()
        self.assertEqual("71", self.outputs()["tooling_artifact_id"])
        self.assertEqual("sha256:" + "e" * 64, self.outputs()["tooling_artifact_sha256"])
        self.assertEqual(canonical_json_bytes(producer).decode().strip(),
                         self.outputs()["tooling_transport_producer"])
        retained_report = json.loads(
            (destination / "tooling-discovery/discovery.json").read_bytes())
        self.assertEqual(report["selected"], retained_report["selected"])
        self.assertEqual(str(destination / "tooling-discovery/capture/evidence"),
                         retained_report["toolingPolicy"]["evidence"])
        request = json.loads((destination / "request.json").read_bytes())
        self.assertNotIn("sdkValidationTooling", request)
        self.assertNotIn("toolingPolicy", request)

    def test_no_hit_drops_only_catalog_proof_and_preserves_explicit_input_behavior(self):
        instance = PhaseInstanceId("sdk", "dart", "metadata", "common")
        catalog_root = self.root / "catalog-sdk"
        explicit = self.root / "explicit-sdk"
        report = {"schemaVersion": 1, "selected": None, "attempts": [], "toolingPolicy": None}

        def capture(roots, kwargs):
            self.assertEqual((explicit,), roots)
            self.assertIsNone(kwargs["tooling"])
            raise ValueError("explicit SDK proof still requires its normal admission")

        with self.assertRaisesRegex(ValueError, "normal admission"):
            self.run_discovery(
                instance, catalogs=(self.catalog(catalog_root),), report=report,
                explicit=(explicit,), capture_side_effect=capture,
            )
        self.assertEqual("", self.outputs()["tooling_artifact_id"])
        self.assertEqual("", self.outputs()["tooling_artifact_sha256"])
        self.assertEqual("", self.outputs()["tooling_transport_producer"])

    def test_unauthorized_and_non_sdk_closures_never_auto_discover(self):
        sdk = PhaseInstanceId("sdk", "rust", "validation", "linux-x64")
        unauthorized = impact_plan(changed=["known.kt"])
        unauthorized["remoteBuildAuthorized"] = False
        result, _, events, tooling = self.run_discovery(
            sdk, plan=unauthorized, report=None, destination_name="unauthorized",
        )
        self.assertEqual("remote-build-unauthorized", result["reason"])
        self.assertEqual([], events)
        tooling.assert_not_called()

        contract = PhaseInstanceId("contract", "contract", "binary", "common")
        roots = []
        result, _, events, tooling = self.run_discovery(
            contract, catalogs=(self.catalog(self.root / "unrequested-sdk"),), report=None,
            destination_name="contract-only", capture_side_effect=lambda selected, _policy: roots.extend(selected) or [],
        )
        self.assertEqual("stop-after-tooling", result["reason"])
        self.assertEqual(["catalogs", "capture"], events)
        self.assertEqual([], roots)
        tooling.assert_not_called()

    def test_automatic_and_explicit_options_are_exact_and_mutually_exclusive(self):
        plan = impact_plan(changed=["known.kt"])
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        cases = (
            {"tooling_java_executable": self.java},
            {"tooling_workflow_sha": WORKFLOW_PIN},
            {"tooling_java_executable": self.java, "tooling_workflow_sha": WORKFLOW_PIN,
             "sdk_validation_tooling": {"explicit": "caller"}},
        )
        for number, options in enumerate(cases):
            destination = self.root / f"invalid-{number}"
            with self.subTest(options=tuple(options)), self.assertRaisesRegex(ValueError, "Automatic tooling"):
                product_reuse.discover(
                    self.plan_path, destination, self.output,
                    repository_root=self.root, environ={}, **options,
                )
            self.assertFalse(destination.exists())

    def test_global_listing_hint_filter_is_exact_newest_first_and_deduplicated(self):
        name = lambda tree, attempt: f"codex-agent-release-tooling-{tree}-attempt-{attempt}"
        artifacts = [
            {"id": 7, "name": name("a" * 40, 1), "expired": False, "workflow_run": {"id": 31}},
            {"id": 11, "name": name("b" * 40, 2), "expired": False, "workflow_run": {"id": 29}},
            {"id": 9, "name": name("c" * 40, 3), "expired": False, "workflow_run": {"id": 31}},
            {"id": 13, "name": name("d" * 40, 4), "expired": True, "workflow_run": {"id": 27}},
            {"id": 15, "name": "unrelated", "expired": False, "workflow_run": {"id": 25}},
            {"id": True, "name": name("e" * 40, 5), "expired": False, "workflow_run": {"id": 23}},
            {"id": 17, "name": name("f" * 40, 6), "expired": False, "workflow_run": {"id": 0}},
        ]
        self.assertEqual((29, 31), tooling_discovery.candidate_run_ids(artifacts))


if __name__ == "__main__":
    unittest.main()
