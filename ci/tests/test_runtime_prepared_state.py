"""Recorded-state restoration over real synthetic carriers, not hosted admission.

Plan selection and Git version policy are explicit seams. Result validation,
every carrier object/transport and target restoration use the real functions;
no planner, SDK tooling, network or signer is invoked.
"""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_runtime_capture as fixture
from ci import runtime_prepared_state as state
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from products.registry import PhaseInstanceId
from products.restore import store_local_object, write_carrier


class RuntimePreparedStateTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="prepared-state-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "candidate"
        self.repository.mkdir()
        self.original = self.root / "original"
        self.discovery = self.original / "product-resume-state"
        self.target = "linux-x64"
        self.metadata = PhaseInstanceId("runtime", self.target, "metadata", self.target)
        self.other = PhaseInstanceId("runtime", "jvm", "binary", "jvm")
        self.requested = tuple(sorted((self.metadata, self.other)))
        self.closure = state.products._dependency_closure(self.requested)
        self.needed = state.products._dependency_closure((self.metadata,))
        self.producer = {**fixture.PRODUCER, "workflowPath": ".github/workflows/ci.yml"}
        self.plan = {"repository": self.producer["repository"], "validationCommit": self.producer["commit"],
            "validationTree": self.producer["tree"], "event": "pull_request", "pullRequest": self.producer["pullRequest"]}
        self.versions = {"contract": "0.2.0", "runtime-release": "0.2.7", "runtime-compatibility": "0.2.0", "sdk": "0.2.0"}
        self.request = {"schemaVersion": 1, "requestType": "reuse-wave", "repository": self.plan["repository"],
            "pullRequest": self.plan["pullRequest"], "repositoryRoot": "/original/checkout",
            "artifactRoot": "/original/checkout/build/product-reuse", "repositoryRevision": self.plan["validationCommit"],
            "requested": [state.products._identity_record(identity) for identity in self.requested],
            "versions": self.versions, "phaseAuthorities": [], "contractEvidence": None,
            "runtimeValidationEvidence": [], "availableObjects": [], "catalogs": {}}
        self.write(self.discovery / "producer.json", self.producer)
        self.write(self.discovery / "reuse-wave-request.json", self.request)
        self.discovery.joinpath("empty-diagnostic.log").write_bytes(b"")
        self.sources, self.receipts, phases = {}, {}, []
        for identity in self.closure:
            directory = self.root / "phase-fixtures" / "-".join((identity.product, identity.component, identity.phase, identity.target))
            stage = directory / "stage"
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/synthetic.bin").write_bytes(str(identity).encode())
            version = "0.2.0" if identity.product == "contract" else "0.2.7"
            manifest = write_output_manifest(stage, identity.product, identity.component, identity.phase,
                identity.target, version, {"fixture": "outputs"})
            receipt_path = directory / "phase-receipt.json"
            receipt = fixture.write_receipt(receipt_path, product=identity.product, component=identity.component,
                phase=identity.phase, target=identity.target, version=version, outputs=manifest["outputs"],
                upstream=[], context={"producer": self.producer})
            stored = store_local_object(stage, receipt_path, self.root / "cache")
            self.sources[identity] = stored["path"]
            self.receipts[identity] = receipt_path.read_bytes()
            phases.append({**state.products._identity_record(identity), "buildKey": receipt["buildKey"],
                "state": "reused", "source": "stable", "transportSource": {"kind": "stable",
                    "indexSha256": "sha256:" + "c" * 64, "artifactName": "synthetic/catalog.zip",
                    "artifactSha256": "sha256:" + "d" * 64}, "receiptSha256": sha256_bytes(self.receipts[identity]),
                "objectSha256": stored["objectSha256"], "misses": []})
        self.result = {"schemaVersion": 1, "result": "complete", "fullReuse": True,
            "phases": phases, "matrices": {"contract": [], "runtime": [], "sdk": []}, "continuationRequirements": []}
        self.write(self.discovery / "reuse-wave-result.json", self.result)
        self.carrier(self.discovery, self.result, self.closure)
        self.selected = next(deepcopy(value) for value in phases if state.products._identity(value) == self.metadata)
        self.selection = {"producer": deepcopy(self.producer), "target": self.target, "metadata": self.selected}
        self.key = self.selected["buildKey"]
        self.patch_requested = self.mock(state.products, "_requested", return_value=self.requested)
        self.patch_versions = self.mock(state.products, "_versions", return_value=self.versions)
        self.patch_source = self.mock(state, "sdk_runtime_source", return_value=None)
        self.no_replay = self.mock(state.products, "_verified_product_state", side_effect=AssertionError("no replay"))
        self.no_planner = self.mock(state.products, "_plan_with_sdk_tooling", side_effect=AssertionError("no planner"))

    def mock(self, owner, name, **kwargs):
        value = patch.object(owner, name, **kwargs)
        mocked = value.start()
        self.addCleanup(value.stop)
        return mocked

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json_bytes(value))

    def carrier(self, directory, result, materialized):
        resolution = {name: deepcopy(result[name]) for name in ("schemaVersion", "result", "fullReuse", "phases", "matrices")}
        resolution.update(result="complete", fullReuse=True, matrices={"contract": [], "runtime": [], "sdk": []})
        resolution["phases"] = [value for value in resolution["phases"] if state.products._identity(value) in materialized]
        write_carrier(directory / ("carrier" if result["fullReuse"] else "reused-carrier"), resolution, materialized,
            {identity: self.sources[identity] for identity in materialized}, {"kind": "ci", "producer": self.producer})

    def invoke(self, **changes):
        arguments = {"producer": self.producer, "target": self.target, "expected_build_key": self.key,
            "selection": self.selection, "state_wave": 0, "repository_root": self.repository}
        arguments.update(changes)
        return state.restore_prepared_runtime_originals(self.plan, self.original, self.root / "output", **arguments)

    def test_verifies_all_objects_but_restores_only_target_closure_with_exact_original_receipts(self):
        before = regular_file_inventory(self.original, allow_empty=True)
        with patch.object(state, "verify_carrier", wraps=state.verify_carrier) as carrier:
            result = self.invoke()
            carrier.assert_called_once_with(self.discovery / "carrier", self.closure,
                {"kind": "ci", "producer": self.producer}, object_root=self.discovery)
        self.assertEqual(set(self.needed), set(result))
        self.assertNotIn(self.other, result)
        for identity, original in result.items():
            self.assertEqual({"stage", "receiptPath", "receipt", "receiptBytes"}, set(original))
            self.assertEqual(self.receipts[identity], original["receiptBytes"])
            self.assertEqual(original["receiptBytes"], original["receiptPath"].read_bytes())
            self.assertEqual(original["receiptBytes"], canonical_json_bytes(original["receipt"]))
            self.assertTrue(original["stage"].is_relative_to(self.root / "output"))
        self.patch_versions.assert_called_once_with(self.repository, self.plan["validationCommit"])
        self.patch_source.assert_called_once_with(self.repository, self.plan["validationCommit"], instances=self.closure,
            runtime_version="0.2.7", sdk_version="0.2.0")
        self.assertEqual(before, regular_file_inventory(self.original, allow_empty=True))
        self.no_replay.assert_not_called()
        self.no_planner.assert_not_called()

    def test_advanced_partial_result_accepts_complete_target_and_not_unrelated_pending_phase(self):
        result = deepcopy(self.result)
        other = next(value for value in result["phases"] if state.products._identity(value) == self.other)
        other.update(state="build", source=None, transportSource=None, receiptSha256=None, objectSha256=None,
            misses=[{"source": source, "reason": "synthetic miss"} for source in state.products.SOURCES])
        result.update(result="build-required", fullReuse=False)
        result["matrices"]["runtime"] = [{**state.products._identity_record(self.other), "buildKey": other["buildKey"]}]
        advanced = self.original / "runtime-state"
        self.write(advanced / "reuse-wave-result.json", result)
        self.carrier(advanced, result, self.needed)
        self.assertEqual(set(self.needed), set(self.invoke(state_wave=4)))

    def test_wrong_producer_request_git_policy_selection_or_result_rejects_before_restore(self):
        mutations = ("producer", "request", "versions", "source", "selection", "result-key", "incomplete")
        for mutation in mutations:
            self.write(self.discovery / "producer.json", self.producer)
            self.write(self.discovery / "reuse-wave-request.json", self.request)
            self.write(self.discovery / "reuse-wave-result.json", self.result)
            selection = deepcopy(self.selection)
            if mutation == "producer":
                self.write(self.discovery / "producer.json", {**self.producer, "runAttempt": 9})
            elif mutation in {"request", "versions", "source"}:
                request = deepcopy(self.request)
                if mutation == "request":
                    request["requested"] = request["requested"][:-1]
                elif mutation == "versions":
                    request["versions"]["sdk"] = "9.0.0"
                else:
                    request["sdkRuntimeSource"] = "released-default"
                self.write(self.discovery / "reuse-wave-request.json", request)
            elif mutation == "selection":
                selection["metadata"]["objectSha256"] = "sha256:" + "f" * 64
            else:
                result = deepcopy(self.result)
                metadata = next(value for value in result["phases"] if state.products._identity(value) == self.metadata)
                if mutation == "result-key":
                    metadata["objectSha256"] = "sha256:" + "f" * 64
                    selection["metadata"] = deepcopy(metadata)
                else:
                    result["phases"] = result["phases"][:-1]
                self.write(self.discovery / "reuse-wave-result.json", result)
            with self.subTest(mutation=mutation), patch.object(state, "restore_object") as restore:
                with self.assertRaises(ValueError):
                    self.invoke(selection=selection)
                restore.assert_not_called()
                self.assertFalse((self.root / "output").exists())

    def test_unrelated_materialized_object_tamper_and_late_original_mutation_cannot_publish(self):
        record = next(value for value in self.result["phases"] if state.products._identity(value) == self.other)
        archive = self.discovery / "carrier" / state.object_relative_path(record["buildKey"], record["receiptSha256"])
        raw = archive.read_bytes()
        archive.write_bytes(raw + b"tampered")
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertFalse((self.root / "output").exists())
        archive.write_bytes(raw)
        restore = state.restore_object
        def changed(*args, **kwargs):
            result = restore(*args, **kwargs)
            (self.discovery / "empty-diagnostic.log").write_bytes(b"changed original diagnostics")
            return result
        with patch.object(state, "restore_object", side_effect=changed), self.assertRaises(ValueError):
            self.invoke()
        self.assertFalse((self.root / "output").exists())


if __name__ == "__main__":
    unittest.main()
