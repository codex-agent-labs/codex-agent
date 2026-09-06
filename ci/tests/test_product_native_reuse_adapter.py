"""Offline outer handoff fixtures; no hosted execution or continuation acceptance."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_product_reuse_adapter as adapter_fixture
from ci.tests.test_product_native_chain import build_chain
from ci.products.inventory import regular_file_inventory, snapshot_regular_tree


adapter = adapter_fixture.product_reuse
canonical_json_bytes = adapter_fixture.canonical_json_bytes
sha256_bytes = adapter_fixture.sha256_bytes


def runtime_record(target="linux-x64", prefix="runtime"):
    return {
        "target": target, "stageRoot": f"{prefix}/stages",
        "phaseReceipts": {phase: f"{prefix}/{target}/{phase}.json"
                          for phase in ("binary", "package", "validation", "metadata")},
        "payload": f"{prefix}/{target}/variant.zip", "attestation": f"{prefix}/{target}/attestation.json",
        "attestationSignature": f"{prefix}/{target}/attestation.sig", "publicKey": f"{prefix}/{target}/key.pub",
        "keyring": None, "keysDirectory": None,
    }


def comparison_record(digest=None, prefix="original"):
    return {
        "receiptSha256": digest or sha256_bytes(prefix.encode()),
        "contractEvidence": {
            "stageRoot": f"{prefix}/contract/stage", "phaseReceipt": f"{prefix}/contract/receipt.json",
            "attestation": f"{prefix}/contract/attestation.json",
            "attestationSignature": f"{prefix}/contract/attestation.sig",
            "publicKey": f"{prefix}/contract/key.pub", "expectedTrustDomain": "development",
            "keyring": None, "keysDirectory": None,
        },
        "runtimeEvidence": runtime_record(prefix=f"{prefix}/runtime"),
    }


def rebase_expected(value, prefix, key=None):
    if isinstance(value, dict):
        return {name: rebase_expected(member, prefix, name) for name, member in value.items()}
    if isinstance(value, list):
        return [rebase_expected(member, prefix) for member in value]
    if value is None or key in {"target", "receiptSha256", "expectedTrustDomain"}:
        return value
    return f"{prefix}/{value}"


class NativeReuseAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="native-reuse-adapter-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.discovery = self.root / "discovery"
        self.discovery.mkdir()

    def test_exact_nested_paths_rebase_without_losing_original_receipt_identity(self):
        runtime = [runtime_record("linux-arm64"), runtime_record()]
        comparisons = sorted([comparison_record(prefix="first"), comparison_record(prefix="second")],
                             key=lambda record: record["receiptSha256"])
        for records, comparison in ((runtime, False), (comparisons, True)):
            original = copy.deepcopy(records)
            actual = adapter._rebase_native_evidence_paths(records, self.discovery, self.root, comparison=comparison)
            self.assertEqual(rebase_expected(records, "discovery"), actual)
            self.assertEqual(original, records)
        self.assertEqual(2, len({record["receiptSha256"] for record in comparisons}))
        self.assertEqual({"linux-x64"}, {record["runtimeEvidence"]["target"] for record in comparisons})
        self.assertEqual([], adapter._rebase_native_evidence_paths([], self.discovery, self.root))

    def test_malformed_duplicate_unsorted_and_unsafe_nested_records_fail(self):
        for comparison in (False, True):
            record = comparison_record() if comparison else runtime_record()
            malformed = [{}, {**record, "unknown": "field"}]
            for value in (None, {}, [record, record], *([item] for item in malformed)):
                with self.subTest(comparison=comparison, value=value), self.assertRaises(ValueError):
                    adapter._rebase_native_evidence_paths(value, self.discovery, self.root, comparison=comparison)
            for bad in ("../escape", "/absolute", "x/../file", "x\\file", "C:relative", "x//file"):
                changed = copy.deepcopy(record)
                runtime = changed["runtimeEvidence"] if comparison else changed
                runtime["phaseReceipts"]["validation"] = bad
                with self.subTest(comparison=comparison, bad=bad), self.assertRaises(ValueError):
                    adapter._rebase_native_evidence_paths([changed], self.discovery, self.root, comparison=comparison)
            pair = (sorted([comparison_record(prefix="first"), comparison_record(prefix="second")],
                           key=lambda item: item["receiptSha256"]) if comparison else
                    [runtime_record("linux-arm64"), runtime_record()])
            with self.assertRaises(ValueError):
                adapter._rebase_native_evidence_paths(list(reversed(pair)), self.discovery, self.root, comparison=comparison)
        with self.assertRaises(ValueError):
            adapter._rebase_native_evidence_paths([runtime_record()], self.root.parent / "outside", self.root)

    def test_catalog_wave_request_forwards_receipt_qualified_comparison_records(self):
        records = tuple(sorted([comparison_record(prefix="first"), comparison_record(prefix="second")],
                               key=lambda item: item["receiptSha256"]))
        request_catalog = {
            "manifest": "catalog/index.json", "signature": "catalog/index.sig", "publicKey": "catalog/key.pub",
            "keyring": None, "keysDirectory": None, "contractAttestation": None,
            "contractAttestationSignature": None, "contractPublicKey": None, "objects": [],
        }
        catalog = adapter.Catalog("same-pr", {}, sha256_bytes(b"synthetic catalog"), request_catalog, {},
                                  native_runtime_evidence=records)
        plain = adapter.Catalog("same-pr", {}, sha256_bytes(b"plain catalog"), request_catalog, {})
        plan = adapter_fixture.impact_plan(changed=["codex-agent-bindings/python/tests/example.py"])
        instance = adapter_fixture.PhaseInstanceId("sdk", "python", "package", "desktop")
        arguments = (plan, self.root, self.discovery, (instance,), adapter_fixture.VERSIONS, [])
        request = adapter._wave_request(*arguments, [catalog], None)
        self.assertEqual(list(records), request["nativeRuntimeComparisonEvidence"])
        self.assertEqual(request_catalog, request["catalogs"]["samePr"])
        ordinary = adapter._wave_request(*arguments, [plain], None)
        self.assertEqual([], ordinary.get("nativeRuntimeComparisonEvidence", []))
        self.assertEqual((), plain.native_runtime_evidence)

    def test_advance_products_forwards_both_fields_before_any_planning_or_materialization(self):
        # Stop at the planner boundary. This deliberately does not claim a complete continuation.
        plan = adapter_fixture.impact_plan(changed=["codex-agent-bindings/python/tests/example.py"])
        instance = adapter_fixture.PhaseInstanceId("sdk", "python", "package", "desktop")
        environment = {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"}
        producer = adapter._consumer(plan, environment)["producer"]
        runtime, comparisons = [runtime_record()], [comparison_record()]
        request = {
            "schemaVersion": 1, "requestType": "reuse-wave", "repository": plan["repository"], "pullRequest": 31,
            "repositoryRoot": str(self.root), "repositoryRevision": plan["validationCommit"],
            "artifactRoot": str(self.root / "build/product-reuse"),
            "requested": [adapter._identity_record(instance)], "versions": adapter_fixture.VERSIONS,
            "phaseAuthorities": [], "contractEvidence": None, "runtimeValidationEvidence": [],
            "nativeRuntimeEvidence": runtime, "nativeRuntimeComparisonEvidence": comparisons, "availableObjects": [],
            "catalogs": {"stable": [], "promotedMain": None, "samePr": None, "local": None},
        }
        (self.discovery / "producer.json").write_bytes(canonical_json_bytes(producer))
        (self.discovery / "reuse-wave-request.json").write_bytes(canonical_json_bytes(request))
        class ReachedPlanner(Exception):
            pass
        def planner(actual, **_kwargs):
            self.assertEqual(str(self.root), actual["artifactRoot"])
            self.assertEqual(rebase_expected(runtime, "discovery"), actual["nativeRuntimeEvidence"])
            self.assertEqual(rebase_expected(comparisons, "discovery"), actual["nativeRuntimeComparisonEvidence"])
            raise ReachedPlanner()
        with patch.object(adapter, "_validate_plan", return_value=plan), \
                patch.object(adapter, "_requested", return_value=(instance,)), \
                patch.object(adapter, "_authorities", return_value=([], None)), \
                patch.object(adapter, "_versions", return_value=adapter_fixture.VERSIONS), \
                patch.object(adapter, "plan_reuse_wave", side_effect=planner) as called, \
                self.assertRaises(ReachedPlanner):
            adapter.advance_products(self.root / "plan.json", self.discovery, None, [], self.root / "advanced",
                                     self.root / "output", repository_root=self.root, environ=environment)
        called.assert_called_once()

    def test_cli_forwards_explicit_native_evidence_roots_to_both_entry_points(self):
        common = ["--plan", "plan.json", "--destination", "next", "--github-output", "output",
                  "--native-runtime-evidence", "original-a", "--native-runtime-evidence", "original-b"]
        roots = (Path("original-a"), Path("original-b"))
        with patch.object(adapter, "discover") as discover:
            self.assertEqual(0, adapter.main(["discover", *common]))
        discover.assert_called_once_with(Path("plan.json"), Path("next"), Path("output"),
                                         native_evidence_roots=roots)
        with patch.object(adapter, "advance_products") as advance:
            self.assertEqual(0, adapter.main([
                "advance-products", *common, "--discovery-root", "discovery", "--state-root", "state",
                "--phase-shard", "shard-a", "--phase-shard", "shard-b",
            ]))
        advance.assert_called_once_with(Path("plan.json"), Path("discovery"), Path("state"),
                                        [Path("shard-a"), Path("shard-b")], Path("next"), Path("output"),
                                        native_evidence_roots=roots)

    def test_evidence_only_discovery_wait_preserves_control_producer(self):
        plan = adapter_fixture.impact_plan(changed=["codex-agent-bindings/python/tests/example.py"])
        instance = adapter_fixture.PhaseInstanceId("sdk", "python", "package", "desktop")
        environment = {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"}
        wait = {"schemaVersion": 1, "result": "build-required", "fullReuse": False,
                "phases": [{**adapter._identity_record(instance), "state": "waiting"}],
                "matrices": {"contract": [], "runtime": [], "sdk": []}, "continuationRequirements": []}
        destination = self.root / "evidence-wait"
        with patch.object(adapter, "_validate_plan", return_value=plan), \
                patch.object(adapter, "_requested", return_value=(instance,)), \
                patch.object(adapter, "_authorities", return_value=([], None)), \
                patch.object(adapter, "_versions", return_value=adapter_fixture.VERSIONS), \
                patch.object(adapter, "_release_trust", return_value=None), \
                patch.object(adapter, "_discover_catalogs", return_value=[]), \
                patch.object(adapter, "_contract_evidence", return_value=None), \
                patch.object(adapter, "plan_reuse_wave", side_effect=[{"fullReuse": True}, wait]):
            adapter.discover(self.root / "plan.json", destination, self.root / "output",
                             repository_root=self.root, environ=environment)
        # Control-flow fixture only: zero ready plans must not lose the current
        # consumer provenance required by advance-products, even during a wait.
        self.assertEqual(canonical_json_bytes(adapter._consumer(plan, environment)["producer"]),
                         (destination / "producer.json").read_bytes())
        self.assertFalse((destination / "phase-plans").exists())


class SignedNativeReuseRebaseTest(unittest.TestCase):
    def test_relocated_public_kr_closure_verifies_without_original_paths_or_private_keys(self):
        # Real signatures over synthetic local products; no network or hosted proof.
        from products.reuse import _native_comparison_provider
        with tempfile.TemporaryDirectory(prefix="signed-native-rebase-") as temporary:
            root = Path(temporary).resolve()
            chain = build_chain(root / "source", 193)
            public = root / "public"
            public.mkdir()
            def file(source, destination):
                path = public / destination
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(source.read_bytes())
                return destination
            contract, variants = chain["contract"], chain["variants"]
            snapshot_regular_tree(contract["payload"].parent.parent, public / "contract/stage")
            snapshot_regular_tree(contract["execution_closure"], public / "contract/trust/execution-closure")
            snapshot_regular_tree(variants["stages"], public / "runtime/stages")
            record = comparison_record()
            record["contractEvidence"] = {
                "stageRoot": "contract/stage", "phaseReceipt": file(contract["receipt"], "contract/receipt.json"),
                "attestation": file(contract["attestation"], f"contract/trust/{contract['attestation'].name}"),
                "attestationSignature": file(contract["signature"], f"contract/trust/{contract['signature'].name}"),
                "publicKey": file(chain["context"]["public_key"], "contract/trust/key.pub"),
                "expectedTrustDomain": "development", "keyring": None, "keysDirectory": None,
            }
            runtime = runtime_record()
            runtime["phaseReceipts"] = {
                phase: file(path, f"runtime/linux-x64/{phase}.json")
                for phase, path in variants["variant_phase_receipts"]["linux-x64"].items()
            }
            for field, sources in (("payload", "variant_bundles"), ("attestation", "variant_attestations"),
                                   ("attestationSignature", "variant_attestation_signatures"),
                                   ("publicKey", "variant_public_keys")):
                source = variants[sources]["linux-x64"]
                runtime[field] = file(source, f"runtime/trust/{source.name}")
            record["runtimeEvidence"] = runtime
            raw = variants["variant_phase_receipts"]["linux-x64"]["validation"].read_bytes()
            record["receiptSha256"] = sha256_bytes(raw)
            original = regular_file_inventory(public)
            relocated = root / "relocated"
            public.rename(relocated)
            # Remove old paths from reach without deleting any original evidence.
            chain["root"].rename(root / "source-unavailable")
            rebased = adapter._rebase_native_evidence_paths([record], relocated, root, comparison=True)
            provider = _native_comparison_provider(root, rebased)
            proof = provider({"receiptSha256": sha256_bytes(raw), "target": "linux-x64"}, None)
            self.assertEqual("linux-x64", proof.target)
            self.assertEqual(original, regular_file_inventory(relocated))
            self.assertFalse((relocated / "keys/development-ed25519").exists())
            # This directly tests the already-object-verified callback; catalog object binding is S792.


if __name__ == "__main__":
    unittest.main()
