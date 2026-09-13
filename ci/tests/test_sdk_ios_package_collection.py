"""iOS package wave isolation over real shards and synthetic workflow seams.

Existing shard, ZIP and collection verification is real.  Workflow composition
substitutes replay/HTTP and does not claim Apple execution or package admission.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow
from ci.tests import test_sdk_worker_collection as fixture
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive
from products.inventory import regular_file_inventory
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


adapter, PhaseInstanceId, PIN = fixture.adapter, fixture.PhaseInstanceId, fixture.PIN
IOS_PACKAGE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")


class SdkIosPackageCollectionTest(unittest.TestCase):
    # Delegate only setup and official API mechanics, never collected test methods.
    setUp = fixture.SdkWorkerCollectionTest.setUp
    names = fixture.SdkWorkerCollectionTest.names
    state = fixture.SdkWorkerCollectionTest.state
    official_api = fixture.SdkWorkerCollectionTest.official_api

    def shard(self):
        self.counter += 1
        base = self.repository / f"build/original-ios-package-{self.counter}"
        stage = base / "stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/sdk-ios-package.bin").write_bytes(b"synthetic iOS package bytes\x00\xff")
        manifest = write_output_manifest(
            stage, "sdk", "sdk-ios", "package", "ios", "0.3.0", {"package": "outputs"},
        )
        receipt = write_receipt(
            base / "fixture-receipt.json", product="sdk", component="sdk-ios",
            phase="package", target="ios", outputs=manifest["outputs"], upstream=[],
            version="0.3.0", version_identity="0.3.0", context={"producer": self.producer},
        )
        ready = {name: receipt[name] for name in PHASE_PLAN_KEYS}
        original = base / "shard"
        descriptor = finalize_phase_object(
            stage_root=stage, phase_plan=ready, producer=self.producer,
            product_version="0.3.0", trust_domain="development", destination=original,
        )
        files = {
            "shard/" + row["relativePath"]: (original / row["relativePath"]).read_bytes()
            for row in regular_file_inventory(original)
        }
        files.update({
            "gradle.log": b"", "execution.json": b'{"synthetic":"not host evidence"}\n',
            "inputs/original.bin": b"retained package input\x00\xff",
        })
        return ready, original, descriptor, files

    def collect(self, elected, uploads, destination):
        with patch.object(adapter, "_verified_product_state", return_value=self.state(elected)), \
                self.official_api(elected, uploads):
            return adapter.collect_runtime_workers(
                self.plan_path, self.discovery, self.discovery, destination,
                trusted_workflow_sha=PIN, repository_root=self.repository,
                environ=self.environment, token="synthetic-token", sdk_family="ios-package",
            )

    def test_only_exact_ios_package_shard_is_collected_and_preserved(self):
        ready, shard, descriptor, files = self.shard()
        unrelated = {
            PhaseInstanceId(*identity): {"buildKey": "sha256:" + "c" * 64}
            for identity in (
                ("sdk", "sdk-ios", "binary", "ios"),
                ("sdk", "javascript", "package", "node"),
                ("sdk", "javascript", "metadata", "node"),
                ("sdk", "python", "package", "desktop"),
                ("runtime", "runtime-aggregate", "metadata", "aggregate"),
            )
        }
        raw = archive(files)
        destination = self.repository / "build/collected-ios-package"
        result = self.collect({IOS_PACKAGE: ready, **unrelated}, {IOS_PACKAGE: raw}, destination)
        row, = result["rows"]
        self.assertEqual("success", row["result"])
        self.assertEqual(IOS_PACKAGE, adapter._identity(row))
        self.assertEqual("product-validation / sdk-sdk-ios-package-ios", row["jobName"])
        self.assertEqual(
            f"codex-agent-sdk-worker-sdk-ios-package-ios-{ready['buildKey'].removeprefix('sha256:')}-"
            f"{self.producer['tree']}-attempt-2",
            row["artifactName"],
        )
        restored = destination / row["shardDirectory"]
        self.assertEqual(descriptor["receiptBytes"], (restored / "phase-receipt.json").read_bytes())
        self.assertEqual(regular_file_inventory(shard), regular_file_inventory(restored))
        retained = destination / row["originalDirectory"]
        self.assertEqual(raw, (retained.parent / "transport.zip").read_bytes())
        for name, contents in files.items():
            self.assertEqual(contents, (retained / name).read_bytes(), name)

    def test_missing_package_upload_is_one_retained_failure_not_an_unrelated_failure(self):
        ready, _, _, _ = self.shard()
        other = PhaseInstanceId("sdk", "javascript", "metadata", "node")
        destination = self.repository / "build/missing-ios-package"
        result = self.collect(
            {IOS_PACKAGE: ready, other: {"buildKey": "sha256:" + "d" * 64}}, {}, destination,
        )
        row, = result["rows"]
        self.assertEqual(IOS_PACKAGE, adapter._identity(row))
        self.assertEqual("failure", row["result"])
        self.assertIsNone(row["shardDirectory"])
        self.assertNotIn("javascript", row["artifactName"])

    def test_collection_and_advancement_scopes_are_exact_and_mutually_exclusive(self):
        ready, _, _, _ = self.shard()
        state = self.state({IOS_PACKAGE: ready})
        state.consumer, state.requested, state.closure = {}, (IOS_PACKAGE,), (IOS_PACKAGE,)
        state.rebased_request, state.prior_by_instance = {}, {}
        state.sources, state.prior_carrier_phases = {}, {}
        state.prior = {"phases": [{**adapter._identity_record(IOS_PACKAGE), "state": "build",
                                    "buildKey": ready["buildKey"]}]}
        cases = (
            ("collect", {"sdk_family": "ios-package", "sdk_ios_binary_only": True}),
            ("collect", {"sdk_family": "ios-package", "sdk_javascript_only": True}),
            ("advance", {"sdk_family": "ios-package", "runtime_workers_only": True}),
            ("advance", {"sdk_family": "unknown"}),
        )
        for number, (operation, options) in enumerate(cases):
            destination = self.repository / f"build/invalid-ios-package-{number}"
            with self.subTest(operation=operation, options=options), patch.object(
                adapter, "_verified_product_state", return_value=state,
            ) as replay, self.assertRaisesRegex(ValueError, "mutually exclusive|Unsupported SDK worker family"):
                if operation == "collect":
                    adapter.collect_runtime_workers(
                        self.plan_path, self.discovery, self.discovery, destination,
                        trusted_workflow_sha=PIN, repository_root=self.repository,
                        environ=self.environment, token="synthetic-token", **options,
                    )
                else:
                    adapter.advance_products(
                        self.plan_path, self.discovery, self.discovery, [], destination,
                        self.repository / f"invalid-output-{number}", repository_root=self.repository,
                        environ=self.environment, failed_instances=(IOS_PACKAGE,), **options,
                    )
            if operation == "collect":
                replay.assert_not_called()
            self.assertFalse(destination.exists())


class SdkIosPackageWorkflowCollectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-package-wave-")
        self.addCleanup(temporary.cleanup)
        self.repository = Path(temporary.name).resolve()
        self.plan = self.repository / "impact-plan.json"
        self.plan.write_bytes(b'{"synthetic":"plan"}\n')
        self.discovery = self.repository / "discovery"
        self.state = self.repository / "state"
        self.key = "sha256:" + "a" * 64
        self.package = {
            "product": "sdk", "component": "sdk-ios", "phase": "package",
            "target": "ios", "buildKey": self.key,
        }

    def test_matrix_and_capture_expose_only_package_on_fixed_apple_route(self):
        other = {**self.package, "phase": "binary", "buildKey": "sha256:" + "b" * 64}
        with patch.object(
            workflow.product_reuse, "inspect_products",
            return_value={"readyPlans": [other, self.package]},
        ):
            result = workflow.matrix(
                self.plan, self.discovery, self.state, self.repository / "matrix-output",
                repository_root=self.repository, environ={}, family="ios-package",
            )
        self.assertEqual([{**self.package, "runner": "macos-26", "runnerOs": "macOS",
                           "runnerArch": "ARM64"}], result["include"])

        destination = self.repository / "captured"
        with patch.object(workflow.product_reuse, "capture_runtime_resume_upload") as capture, \
                patch.object(workflow, "matrix", return_value=result) as matrix:
            captured = workflow.capture(
                self.plan, destination, self.repository / "capture-output",
                artifact_id=41, artifact_sha256="sha256:" + "c" * 64,
                trusted_workflow_sha="d" * 40, sdk_state_wave=4,
                repository_root=self.repository, environ={}, token="synthetic-token",
                family="ios-package",
            )
        self.assertEqual(destination / "original/runtime-state", captured["state_root"])
        self.assertEqual(4, capture.call_args.kwargs["sdk_state_wave"])
        self.assertEqual("ios-package", matrix.call_args.kwargs["family"])

    def test_wave_five_collects_only_package_and_preserves_original_state_roots(self):
        original = self.repository / "captured/original"
        for name in ("product-resume-inputs", "product-resume-state", "runtime-state"):
            (original / name).mkdir(parents=True)
            (original / name / "original.bin").write_bytes(name.encode())
        for failed in (False, True):
            destination = self.repository / f"wave-five-{failed}"
            row = {**self.package, "result": "failure" if failed else "success",
                   "shardDirectory": None if failed else "rows/sdk-ios-package/original/shard"}

            def advance(*arguments, **keywords):
                self.assertEqual("ios-package", keywords["sdk_family"])
                self.assertEqual((IOS_PACKAGE,) if failed else (), keywords["failed_instances"])
                self.assertEqual([] if failed else [destination / "collection/rows/sdk-ios-package/original/shard"],
                                 arguments[3])
                arguments[4].mkdir(parents=True)
                return {"synthetic": "advanced"}

            with patch.object(
                workflow.product_reuse, "collect_runtime_workers", return_value={"rows": [row]},
            ) as collect, patch.object(
                workflow.product_reuse, "advance_products", side_effect=advance,
            ), patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
                result = workflow.collect(
                    original, destination, self.repository / f"wave-five-output-{failed}",
                    wave=5, trusted_workflow_sha="d" * 40,
                    repository_root=self.repository, environ={}, token="synthetic-token",
                    family="ios-package",
                )
            self.assertEqual({"synthetic": "advanced"}, result)
            self.assertEqual("ios-package", collect.call_args.kwargs["sdk_family"])
            self.assertEqual(not failed, matrix.called)
            if matrix.called:
                self.assertEqual("ios-package", matrix.call_args.kwargs["family"])
            for name in ("product-resume-inputs", "product-resume-state"):
                self.assertEqual(name.encode(), (destination / "handoff" / name / "original.bin").read_bytes())

        with patch.object(workflow.product_reuse, "collect_runtime_workers") as collect:
            for wave in (3, 4, 6):
                with self.subTest(wave=wave), self.assertRaises(ValueError):
                    workflow.collect(
                        original, self.repository / f"wrong-wave-{wave}", self.repository / f"wrong-output-{wave}",
                        wave=wave, trusted_workflow_sha="d" * 40, repository_root=self.repository,
                        environ={}, token="synthetic-token", family="ios-package",
                    )
            collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
