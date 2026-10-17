"""Transport tests for fresh Apple native inputs; Kotlin owns semantic proof."""

from argparse import Namespace
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import receipt as lane_receipt  # noqa: E402
import reuse as lane_reuse  # noqa: E402
import sdk_apple_native  # noqa: E402
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes  # noqa: E402
from ci.tests import test_ci as ci_fixture  # noqa: E402
from ci.tests.product_chain_support import output, write_receipt  # noqa: E402


def archive_tree(root: Path) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(value for value in root.rglob("*") if value.is_file()):
            archive.writestr(path.relative_to(root).as_posix(), path.read_bytes())
    return output.getvalue()


@contextmanager
def original_qualification_callable(qualify):
    """Mock only helper dispatch; its independent authentication has own tests."""
    spec = SimpleNamespace(loader=mock.Mock())
    with mock.patch.object(sdk_apple_native.importlib.util, "spec_from_file_location",
                           return_value=spec) as lookup, \
            mock.patch.object(sdk_apple_native.importlib.util, "module_from_spec",
                              return_value=SimpleNamespace(qualify_candidate=qualify)):
        yield lookup, spec.loader


class SdkAppleNativeInputsTest(ci_fixture.GitFixture):
    def test_missing_original_toolchain_observations_are_rejected(self):
        for lane, path in sdk_apple_native.NATIVE_TOOLCHAINS.items():
            with self.subTest(lane=lane):
                receipt = json.loads((self.lanes[lane] / "lane-receipt.json").read_text())
                receipt["evidence"] = [
                    item for item in receipt["evidence"] if item["relativePath"] != path
                ]
                with self.assertRaisesRegex(ValueError, "unexpected output inventory"):
                    sdk_apple_native._require_native_records(receipt, lane, self.lanes[lane])

    def setUp(self) -> None:
        super().setUp()
        self.root = self.root.resolve()
        _, self.plan_path, _ = self.make_plan(
            "ios-swift-auth-tests/native-inputs.kt", force_full=True,
        )
        self.plan_path = self.plan_path.resolve()
        self.environment = {"GITHUB_RUN_ID": "91", "GITHUB_RUN_ATTEMPT": "2"}
        self.producer = sdk_apple_native.product_reuse._consumer(
            sdk_apple_native.product_reuse._validate_plan(self.plan_path, self.root),
            self.environment,
        )["producer"]
        self.pin = "c" * 40
        self.token = "not-a-real-token"
        self.lanes = {}
        self.raw = {}
        self.artifacts = {}
        self.contents = {
            "ios-native-tests": {
                next(iter(sdk_apple_native.NATIVE_FILES["ios-native-tests"])):
                    self.proof("synthetic-native-tests"),
            },
            "ios-rust-device": {
                source: (b"!<arch>\nsynthetic-device\n" if source.endswith(".a")
                         else self.proof("synthetic-device-proof"))
                for source in sdk_apple_native.NATIVE_FILES["ios-rust-device"]
            },
            "ios-rust-simulator": {
                source: (b"!<arch>\nsynthetic-simulator\n" if source.endswith(".a")
                         else self.proof("synthetic-simulator-proof"))
                for source in sdk_apple_native.NATIVE_FILES["ios-rust-simulator"]
            },
        }
        for lane, path in sdk_apple_native.NATIVE_TOOLCHAINS.items():
            self.contents[lane][path] = b'{"scope":"synthetic transport-only observations"}\n'
        for index, lane in enumerate(sdk_apple_native.LANES, 1):
            root = self.root / "uploads" / lane
            for relative, contents in self.contents[lane].items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
            (root / "lane-result.txt").write_text(f"lane={lane}\nresult=passed\n")
            artifacts = [
                f"{relative}={'rust-archive' if relative.endswith('.a') else 'rust-proof'}"
                for relative in self.contents[lane]
                if relative.endswith(".a")
            ]
            evidence = [
                f"{relative}={'rust-toolchain-evidence' if relative.endswith('-toolchain.json') else 'native-test-proof' if lane == 'ios-native-tests' else 'rust-proof'}"
                for relative in self.contents[lane]
                if not relative.endswith(".a")
            ] + ["lane-result.txt=lane-result"]
            lane_receipt.create_receipt(Namespace(
                plan=self.plan_path, lane=lane, output=root,
                workflow_path=".github/workflows/ci.yml",
                artifact_name=f"codex-agent-ci-{lane}-{self.producer['tree']}",
                run_id=self.producer["runId"], run_attempt=self.producer["runAttempt"],
                runner=["os=macOS", "arch=ARM64"],
                toolchain=["xcode=26.6", "rust=1.95.0",
                           "validationActions=build,metadata,test"],
                artifact=artifacts, evidence=evidence,
            ))
            raw = archive_tree(root)
            artifact_id = 700 + index
            url = ("https://api.github.com/repos/codex-agent-labs/codex-agent"
                   f"/actions/artifacts/{artifact_id}")
            self.lanes[lane] = root
            self.raw[lane] = raw
            self.artifacts[lane] = {
                "id": artifact_id,
                "name": f"codex-agent-ci-{lane}-{self.producer['tree']}",
                "size_in_bytes": len(raw),
                "digest": sha256_bytes(raw),
                "expired": False,
                "created_at": "2026-09-13T10:10:00Z",
                "archive_download_url": url + "/zip",
                "workflow_run": {
                    "id": self.producer["runId"], "head_sha": self.producer["commit"],
                },
            }
        self.run = {
            "id": self.producer["runId"],
            "run_attempt": self.producer["runAttempt"],
            "path": self.producer["workflowPath"],
            "head_sha": self.producer["commit"],
            "event": self.producer["event"],
            "status": "completed",
            "conclusion": "success",
            "pull_requests": [{
                "number": self.producer["pullRequest"],
                "base": {"sha": "1" * 40}, "head": {"sha": "2" * 40},
            }],
            "repository": {"full_name": self.producer["repository"], "fork": False},
            "head_repository": {"full_name": self.producer["repository"], "fork": False},
            "referenced_workflows": [{
                "path": (f"{self.producer['repository']}/.github/workflows/"
                         f"product-validation.yml@{self.pin}"),
                "sha": self.pin,
            }],
        }
        self.observed_commit = {
            "sha": self.producer["commit"], "tree": {"sha": self.producer["tree"]},
            "parents": [{"sha": "1" * 40}, {"sha": "2" * 40}],
        }
        self.jobs = [{
            "id": 800 + index,
            "name": sdk_apple_native.JOBS[lane],
            "run_id": self.producer["runId"],
            "head_sha": self.producer["commit"],
            "status": "completed", "conclusion": "success",
            "started_at": "2026-09-13T10:00:00Z",
            "completed_at": "2026-09-13T10:20:00Z",
        } for index, lane in enumerate(sdk_apple_native.LANES, 1)]
        self.plan_before = self.plan_path.read_bytes()

    def proof(self, protocol, *, commit=None, tree=None):
        return (json.dumps({"protocol": protocol,
                            "candidateCommit": self.producer["commit"] if commit is None else commit,
                            "candidateTree": self.producer["tree"] if tree is None else tree},
                           sort_keys=True) + "\n").encode()

    def uploads(self):
        return {
            lane: {
                "artifactId": artifact["id"], "artifactSha256": artifact["digest"],
            }
            for lane, artifact in self.artifacts.items()
        }

    def original_binary_receipt(self, *, producer=None, product="sdk", component="sdk-ios",
                                phase="binary", target="ios"):
        path = self.root / "selected-original-binary" / f"{product}-{component}-{phase}-{target}.json"
        write_receipt(
            path, product=product, component=component, phase=phase, target=target,
            version="0.8.0", version_identity="0.8.0",
            outputs=[output("fixture", "outputs/original.bin", b"synthetic original iOS binary")],
            upstream=[], context={"producer": self.producer if producer is None else producer},
        )
        return path

    def invoke(self, *, uploads=None, plan_path=None, environ=None, original_uploads=None,
               original_binary_receipt_path=None):
        def query(url, token):
            self.assertEqual(self.token, token)
            attempt = (f"https://api.github.com/repos/{self.producer['repository']}"
                       f"/actions/runs/{self.producer['runId']}/attempts/{self.producer['runAttempt']}")
            if url == attempt:
                return self.run
            if url == attempt.rsplit("/", 1)[0] + "/1":
                return {**self.run, "run_attempt": 1}
            if url == (f"https://api.github.com/repos/{self.producer['repository']}"
                       f"/git/commits/{self.producer['commit']}"):
                return self.observed_commit
            for artifact in self.artifacts.values():
                if url == artifact["archive_download_url"].removesuffix("/zip"):
                    return artifact
            raise AssertionError(f"Unexpected API query: {url}")

        def listing(url, key, token):
            self.assertEqual(self.token, token)
            if original_uploads is not None and key == "artifacts":
                self.assertEqual(
                    f"https://api.github.com/repos/{self.producer['repository']}"
                    "/actions/runs/41/artifacts", url)
                return original_uploads
            self.assertEqual("jobs", key)
            prefix = f"https://api.github.com/repos/{self.producer['repository']}/actions/runs/{self.producer['runId']}/attempts/"
            self.assertIn(url, (prefix + "1/jobs", prefix + str(self.producer["runAttempt"]) + "/jobs"))
            return self.jobs

        def download(artifact, token):
            self.assertEqual(self.token, token)
            lane = next(lane for lane, value in self.artifacts.items()
                        if value["id"] == artifact["id"])
            return self.raw[lane]

        patches = (
            mock.patch.object(sdk_apple_native.product_reuse, "api_json", side_effect=query),
            mock.patch.object(sdk_apple_native.product_reuse, "paginated_items", side_effect=listing),
            mock.patch.object(sdk_apple_native.product_reuse, "download_artifact", side_effect=download),
        )
        first = patches[0].__enter__()
        second = patches[1].__enter__()
        third = patches[2].__enter__()
        try:
            context = sdk_apple_native.verified_sdk_apple_native_inputs(
                self.plan_path if plan_path is None else plan_path,
                uploads=self.uploads() if uploads is None else uploads,
                trusted_workflow_sha=self.pin, repository_root=self.root,
                environ=self.environment if environ is None else environ, token=self.token,
                original_binary_receipt_path=original_binary_receipt_path,
            )
            return context, (first, second, third), patches
        except BaseException:
            for patcher in reversed(patches):
                patcher.__exit__(*sys.exc_info())
            raise

    @staticmethod
    def close(patches) -> None:
        for patcher in reversed(patches):
            patcher.__exit__(None, None, None)

    def test_exact_three_uploads_yield_five_flat_files_and_raw_transport(self) -> None:
        context, calls, patches = self.invoke()
        try:
            with context as result:
                expected = {
                    destination: self.contents[lane][source]
                    for lane, paths in sdk_apple_native.NATIVE_FILES.items()
                    for source, destination in paths.items()
                }
                self.assertEqual(set(expected), {path.name for path in result["directory"].iterdir()})
                for name, contents in expected.items():
                    self.assertEqual(contents, (result["directory"] / name).read_bytes())
                for lane in sdk_apple_native.LANES:
                    self.assertEqual(
                        self.raw[lane],
                        (result["captureRoot"] / "archives" / f"{lane}.zip").read_bytes(),
                    )
                    self.assertEqual(
                        (self.lanes[lane] / "lane-receipt.json").read_bytes(),
                        result["receiptBytes"][lane],
                    )
                self.assertEqual(self.producer, result["transport"]["captureProducer"])
                self.assertEqual(
                    {lane: self.producer for lane in sdk_apple_native.LANES},
                    result["originalProducers"],
                )
                self.assertEqual(set(sdk_apple_native.LANES), set(result["transport"]["artifacts"]))
                self.assertEqual(result["inventory"], regular_file_inventory(result["directory"]))
            self.assertEqual((12, 3, 3), tuple(call.call_count for call in calls))
        finally:
            self.close(patches)
        self.assertEqual(self.plan_before, self.plan_path.read_bytes())

    def test_historical_binary_receipt_selects_original_attempt_not_current_environment(self) -> None:
        receipt = self.original_binary_receipt()
        receipt_bytes = receipt.read_bytes()
        current_head = self.commit("unrelated-after-original-native-inputs.txt", "new checkout head\n")
        self.assertNotEqual(self.producer["commit"], current_head)
        validator = sdk_apple_native.product_reuse._validate_plan
        with mock.patch.object(
            sdk_apple_native.product_reuse, "_validate_plan", wraps=validator,
        ) as validate:
            context, calls, patches = self.invoke(
                original_binary_receipt_path=receipt,
                environ={"GITHUB_RUN_ID": "unrelated", "GITHUB_RUN_ATTEMPT": "not-original"},
            )
            try:
                with context as result:
                    self.assertEqual(self.producer, result["producer"])
                    self.assertEqual(self.producer, result["transport"]["captureProducer"])
                    self.assertEqual(
                        sha256_bytes(receipt_bytes), result["transport"]["binaryReceiptSha256"],
                    )
                    self.assertEqual(
                        receipt_bytes,
                        (result["captureRoot"] / "original-binary-receipt.json").read_bytes(),
                    )
                    self.assertEqual(self.plan_before, (
                        result["captureRoot"] / "plan/impact-plan.json"
                    ).read_bytes())
                self.assertEqual((12, 3, 3), tuple(call.call_count for call in calls))
            finally:
                self.close(patches)
        self.assertGreaterEqual(validate.call_count, 2)
        self.assertTrue(all(call.kwargs == {"expected_revision": self.producer["commit"]}
                            for call in validate.call_args_list))
        self.assertEqual(receipt_bytes, receipt.read_bytes())
        self.assertEqual(self.plan_before, self.plan_path.read_bytes())

    def test_historical_receipt_requires_exact_binary_identity_before_observation(self) -> None:
        identities = (
            {"phase": "package"}, {"component": "javascript", "target": "node"},
            {"product": "contract", "component": "contract", "phase": "binary", "target": "common"},
        )
        for identity in identities:
            receipt = self.original_binary_receipt(**identity)
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                context, calls, patches = self.invoke(original_binary_receipt_path=receipt)
                try:
                    with context:
                        self.fail("wrong original binary identity yielded Apple native inputs")
                finally:
                    self.close(patches)
            self.assertEqual((0, 0, 0), tuple(call.call_count for call in calls))

    def test_historical_plan_requires_full_original_producer_before_observation(self) -> None:
        receipt = self.original_binary_receipt()
        value = json.loads(receipt.read_bytes())
        value["producer"]["workflowPath"] = ".github/workflows/other.yml"
        receipt.write_bytes(canonical_json_bytes(value))
        context, calls, patches = self.invoke(original_binary_receipt_path=receipt)
        try:
            with self.assertRaisesRegex(ValueError, "differs from the original binary producer"):
                with context:
                    self.fail("cross-paired historical producer yielded Apple native inputs")
            self.assertEqual((0, 0, 0), tuple(call.call_count for call in calls))
        finally:
            self.close(patches)

        historical = {**self.producer, "commit": self.base,
                      "tree": self.git("rev-parse", f"{self.base}^{{tree}}")}
        receipt = self.original_binary_receipt(producer=historical)
        context, calls, patches = self.invoke(original_binary_receipt_path=receipt)
        try:
            with self.assertRaisesRegex(ValueError, "selected revision"):
                with context:
                    self.fail("wrong historical plan revision yielded Apple native inputs")
            self.assertEqual((0, 0, 0), tuple(call.call_count for call in calls))
        finally:
            self.close(patches)

    def test_historical_receipt_and_plan_are_rechecked_through_context_exit(self) -> None:
        mutations = ("receipt", "private receipt", "plan", "private plan")
        for mutation in mutations:
            receipt = self.original_binary_receipt()
            receipt_bytes = receipt.read_bytes()
            plan_bytes = self.plan_path.read_bytes()
            context, _, patches = self.invoke(original_binary_receipt_path=receipt)
            try:
                with self.subTest(mutation=mutation), \
                        self.assertRaisesRegex(ValueError, "changed during use"):
                    with context as result:
                        targets = {
                            "receipt": receipt,
                            "private receipt": result["captureRoot"] / "original-binary-receipt.json",
                            "plan": self.plan_path,
                            "private plan": result["captureRoot"] / "plan/impact-plan.json",
                        }
                        targets[mutation].write_bytes(b"changed during use\n")
            finally:
                self.close(patches)
                receipt.write_bytes(receipt_bytes)
                self.plan_path.write_bytes(plan_bytes)

    def test_upload_identity_window_and_exact_map_reject_before_yield(self) -> None:
        baseline = deepcopy((self.artifacts, self.jobs))
        for case in ("missing", "extra", "duplicate", "digest", "window"):
            self.artifacts, self.jobs = deepcopy(baseline)
            uploads = self.uploads()
            if case == "missing":
                uploads.pop("ios-native-tests")
            elif case == "extra":
                uploads["ios-extra"] = uploads["ios-native-tests"]
            elif case == "duplicate":
                uploads["ios-rust-device"]["artifactId"] = uploads["ios-native-tests"]["artifactId"]
            elif case == "digest":
                uploads["ios-native-tests"]["artifactSha256"] = "sha256:" + "f" * 64
            else:
                self.artifacts["ios-native-tests"]["created_at"] = "2026-09-13T09:59:59Z"
            with self.subTest(case=case), self.assertRaises(ValueError):
                context, _, patches = self.invoke(uploads=uploads)
                try:
                    with context:
                        self.fail("invalid Apple native upload yielded inputs")
                finally:
                    self.close(patches)
        self.assertEqual(self.plan_before, self.plan_path.read_bytes())

    def test_unauthorized_and_dispatch_plans_reject_before_any_http(self) -> None:
        def reject(plan_path: Path) -> None:
            context, calls, patches = self.invoke(plan_path=plan_path.resolve())
            try:
                with self.assertRaisesRegex(ValueError, "authorized PR or merge-group"):
                    with context:
                        self.fail("unauthorized Apple native plan yielded inputs")
                self.assertEqual((0, 0, 0), tuple(call.call_count for call in calls))
            finally:
                self.close(patches)

        _, denied, _ = self.make_plan(
            "ios-swift-auth-tests/unauthorized-native-inputs.kt",
            merge_ready=False, force_full=True,
        )
        reject(denied)
        target = self.commit("ios-swift-auth-tests/dispatch-native-inputs.kt", "dispatch\n")
        tree = self.git("rev-parse", f"{target}^{{tree}}")
        dispatch = self.root / "build/dispatch/impact-plan.json"
        ci_fixture.plan(
            root=self.root, base=self.base, target=target, head=target,
            event="workflow_dispatch", pull_request=None, force_full=True,
            repository="codex-agent-labs/codex-agent", output=dispatch,
            event_payload={
                "repository": {"full_name": "codex-agent-labs/codex-agent"},
                "ref": "refs/heads/apple-native-fixture",
                "inputs": {"baseCommit": self.base, "validationCommit": target,
                           "validationTree": tree},
            },
            github_ref="refs/heads/apple-native-fixture", github_sha=target,
            dispatch_approved=True,
        )
        reject(dispatch)

    def test_cross_paired_receipt_rejects(self) -> None:
        lane = "ios-rust-device"
        root = self.lanes[lane]
        receipt_path = root / "lane-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["runId"] = 99
        receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
        self._repack(lane)
        with self.assertRaisesRegex(ValueError, "consumer context"):
            context, _, patches = self.invoke()
            try:
                with context:
                    self.fail("cross-paired Apple native receipt yielded inputs")
            finally:
                self.close(patches)

    def test_prior_and_mixed_attempt_custodians_preserve_current_consumer(self):
        # Synthetic original CI composition, not genuine hosted evidence.
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                for lane in sdk_apple_native.LANES:
                    path = self.lanes[lane] / "lane-receipt.json"
                    receipt = json.loads(path.read_bytes())
                    receipt["runAttempt"] = 2 if mixed and lane == "ios-rust-device" else 1
                    path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
                    self._repack(lane)
                context, _, patches = self.invoke()
                try:
                    with context as result:
                        self.assertEqual(self.producer, result["producer"])
                        self.assertEqual(self.producer, result["transport"]["captureProducer"])
                        for lane in sdk_apple_native.LANES:
                            expected = 2 if mixed and lane == "ios-rust-device" else 1
                            self.assertEqual(expected, result["originalProducers"][lane]["runAttempt"])
                            self.assertEqual(self.raw[lane], (result["captureRoot"] / "archives" / f"{lane}.zip").read_bytes())
                        retained = self.root / f"prior-attempt-retained-{mixed}"
                        sdk_apple_native.snapshot_regular_tree(result["captureRoot"], retained, allow_empty=True)
                finally:
                    self.close(patches)
                binary_receipt = self.original_binary_receipt()
                context, _, patches = self.invoke(original_binary_receipt_path=binary_receipt,
                    environ={"GITHUB_RUN_ID": "unrelated", "GITHUB_RUN_ATTEMPT": "99"})
                try:
                    with context as historical:
                        self.assertEqual(self.producer, historical["producer"])
                        self.assertEqual(1, historical["originalProducers"]["ios-native-tests"]["runAttempt"])
                        self.assertEqual(sha256_bytes(binary_receipt.read_bytes()),
                                         historical["transport"]["binaryReceiptSha256"])
                finally:
                    self.close(patches)
                with sdk_apple_native.verified_retained_sdk_apple_native_inputs(retained,
                        original_binary_receipt_path=self.original_binary_receipt(),
                        repository_root=self.root) as replay:
                    self.assertEqual(self.producer, replay["producer"])
                    self.assertEqual(1, replay["originalProducers"]["ios-native-tests"]["runAttempt"])

    def test_future_attempt_and_failed_or_ambiguous_original_job_reject(self):
        lane = "ios-native-tests"
        for cause in ("future", "failed", "ambiguous"):
            with self.subTest(cause=cause):
                path = self.lanes[lane] / "lane-receipt.json"
                receipt = json.loads(path.read_bytes())
                receipt["runAttempt"] = 3 if cause == "future" else 1
                path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
                self._repack(lane)
                jobs = self.jobs
                self.jobs = ([{**job, "conclusion": "failure"} for job in jobs] if cause == "failed"
                             else jobs * 2 if cause == "ambiguous" else jobs)
                context, _, patches = self.invoke()
                try:
                    with self.assertRaises(ValueError), context:
                        self.fail("invalid original admitted")
                finally:
                    self.close(patches)
                    self.jobs = jobs

    def test_missing_receipt_bound_native_file_rejects(self) -> None:
        lane = "ios-rust-device"
        source = next(iter(sdk_apple_native.NATIVE_FILES[lane]))
        (self.lanes[lane] / source).unlink()
        self._repack(lane)
        with self.assertRaisesRegex(ValueError, "integrity-mismatched receipt file"):
            context, _, patches = self.invoke()
            try:
                with context:
                    self.fail("incomplete Apple native lane yielded inputs")
            finally:
                self.close(patches)

    def test_mutation_during_use_fails_the_context_recheck(self) -> None:
        context, _, patches = self.invoke()
        try:
            with self.assertRaisesRegex(ValueError, "changed during use"):
                with context as result:
                    (result["directory"] / "native-tests-proof.json").write_bytes(b"changed\n")
        finally:
            self.close(patches)
        self.assertEqual(self.plan_before, self.plan_path.read_bytes())

    def test_reissued_transport_retains_raw_chain_and_binds_original_proof_identity(self) -> None:
        lane = "ios-rust-device"
        original_commit = self.base
        original_tree = self.git("rev-parse", f"{original_commit}^{{tree}}")
        receipt_path = self.lanes[lane] / "lane-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        receipt.update(validationCommit=original_commit, validationTree=original_tree,
                       runId=41, runAttempt=1,
                       artifactName=f"codex-agent-ci-{lane}-{original_tree}")
        for source, destination in sdk_apple_native.NATIVE_FILES[lane].items():
            if destination.endswith(".json"):
                proof = self.proof("synthetic-device-proof", commit=original_commit, tree=original_tree)
                (self.lanes[lane] / source).write_bytes(proof)
                next(item for item in receipt["evidence"] if item["relativePath"] == source)["sha256"] = hashlib.sha256(proof).hexdigest()
        with mock.patch.dict(os.environ, self.environment, clear=False):
            lane_reuse.reissue_transport_receipt(
                self.lanes[lane], receipt, json.loads(self.plan_path.read_text()), lane,
                f"codex-agent-ci-{lane}-{original_tree}",
            )
        self._repack(lane)
        raw_receipt = (self.lanes[lane] / "lane-receipt.json").read_bytes()
        raw_provenance = (self.lanes[lane] / "transport-provenance.json").read_bytes()
        original = {**self.producer, "commit": original_commit, "tree": original_tree,
                    "runId": 41, "runAttempt": 1}
        original_artifact = {"id": 99, "name": f"codex-agent-ci-{lane}-{original_tree}",
                             "expired": False, "digest": "sha256:" + "e" * 64}
        def qualify(arguments, artifact, **kwargs):
            self.assertEqual(lane, arguments.lane)
            self.assertEqual(self.token, arguments.token)
            self.assertEqual(original_artifact, artifact)
            self.assertEqual(self.pin, kwargs["trusted_workflow_sha"])
            self.assertEqual(self.root, kwargs["repository_root"])
            for source in (*sdk_apple_native.NATIVE_FILES[lane], sdk_apple_native.NATIVE_TOOLCHAINS[lane]):
                destination = kwargs["output"] / "lane" / source
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((self.lanes[lane] / source).read_bytes())
            return {"originalProducer": original}
        qualifier = mock.Mock(side_effect=qualify)
        context, _, patches = self.invoke(original_uploads=[original_artifact])
        try:
            with original_qualification_callable(qualifier), context as result:
                qualifier.assert_called_once()
                self.assertEqual(original_commit, result["originalProducers"][lane]["commit"])
                self.assertEqual(original_tree, result["originalProducers"][lane]["tree"])
                captured = result["captureRoot"] / "lanes" / lane
                self.assertEqual(raw_receipt, result["receiptBytes"][lane])
                self.assertEqual(raw_provenance, (captured / "transport-provenance.json").read_bytes())
                self.assertEqual(self.raw[lane], (result["captureRoot"] / "archives" / f"{lane}.zip").read_bytes())
        finally:
            self.close(patches)
        context, _, patches = self.invoke(original_uploads=[original_artifact])
        try:
            rejected = mock.Mock(side_effect=ValueError("original job not authenticated"))
            with original_qualification_callable(rejected), \
                    self.assertRaisesRegex(ValueError, "original job not authenticated"):
                with context:
                    self.fail("native inputs yielded before original source authentication")
            rejected.assert_called_once()
        finally:
            self.close(patches)

    def test_original_native_transport_source_upload_is_unique_and_required(self):
        lane = "ios-native-tests"
        name = f"codex-agent-ci-{lane}-{self.producer['tree']}"
        for artifacts in ([], [{"name": name, "expired": True}],
                          [{"name": name, "expired": False}] * 2):
            with self.subTest(artifacts=artifacts), \
                    mock.patch.object(sdk_apple_native.product_reuse, "paginated_items", return_value=artifacts), \
                    original_qualification_callable(mock.Mock()) as (lookup, _):
                with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
                    sdk_apple_native._authenticate_native_transport_original(
                        self.plan_path, {}, self.producer, lane, self.lanes[lane],
                        root=self.root, token=self.token, trusted_workflow_sha=self.pin)
                lookup.assert_not_called()

    def test_original_native_transport_qualification_arguments_and_rejections(self):
        lane = "ios-rust-simulator"
        artifact = {"id": 99, "name": f"codex-agent-ci-{lane}-{self.producer['tree']}",
                    "expired": False, "digest": "sha256:" + "e" * 64}
        receipt = json.loads((self.lanes[lane] / "lane-receipt.json").read_bytes())
        for failure in (None, "qualifier", "producer", "content"):
            with self.subTest(failure=failure):
                def qualify(arguments, selected, **kwargs):
                    self.assertEqual(self.plan_path, arguments.plan)
                    self.assertEqual(lane, arguments.lane)
                    self.assertEqual(self.token, arguments.token)
                    self.assertEqual([f"{k}={v}" for k, v in receipt["runner"].items()], arguments.runner)
                    self.assertNotIn("validationActions=build,metadata,test", arguments.toolchain)
                    self.assertEqual(artifact, selected)
                    self.assertEqual(self.pin, kwargs["trusted_workflow_sha"])
                    self.assertEqual(self.root, kwargs["repository_root"])
                    if failure == "qualifier":
                        raise ValueError("original successful-job authentication rejected")
                    if failure == "producer":
                        return {"originalProducer": {**self.producer, "runId": 123}}
                    for source in (*sdk_apple_native.NATIVE_FILES[lane], sdk_apple_native.NATIVE_TOOLCHAINS[lane]):
                        target = kwargs["output"] / "lane" / source
                        target.parent.mkdir(parents=True, exist_ok=True)
                        raw = (self.lanes[lane] / source).read_bytes()
                        target.write_bytes(raw + b"different" if failure == "content" else raw)
                    return {"originalProducer": self.producer}
                qualifier = mock.Mock(side_effect=qualify)
                with mock.patch.object(sdk_apple_native.product_reuse, "paginated_items", return_value=[artifact]) as listing, \
                        original_qualification_callable(qualifier) as (lookup, loader):
                    def authenticate():
                        sdk_apple_native._authenticate_native_transport_original(
                            self.plan_path, receipt, self.producer, lane, self.lanes[lane],
                            root=self.root, token=self.token, trusted_workflow_sha=self.pin)
                    if failure is None:
                        authenticate()
                    else:
                        expected = {"qualifier": "successful-job", "producer": "transport provenance",
                                    "content": "differs from authenticated original"}[failure]
                        with self.assertRaisesRegex(ValueError, expected):
                            authenticate()
                    listing.assert_called_once_with(
                        f"https://api.github.com/repos/{self.producer['repository']}/actions/runs/91/artifacts",
                        "artifacts", self.token)
                    lookup.assert_called_once_with("sdk_native_original_qualification",
                        CI_ROOT.parent / ".github/actions/run-ci-lane/sdk_native_qualification.py")
                    loader.exec_module.assert_called_once()
                    qualifier.assert_called_once()

    def test_original_native_authentication_resolves_trusted_temporary_alias(self):
        lane = "ios-rust-device"
        artifact = {"id": 99, "name": f"codex-agent-ci-{lane}-{self.producer['tree']}",
                    "expired": False, "digest": "sha256:" + "e" * 64}
        receipt = json.loads((self.lanes[lane] / "lane-receipt.json").read_bytes())
        temporary = self.root / "original-authentication-temp"
        temporary.mkdir()
        alias = self.root / "temporary-alias"
        alias.symlink_to(temporary, target_is_directory=True)

        def qualify(arguments, selected, **kwargs):
            sdk_apple_native.snapshot_regular_tree(
                self.lanes[lane], kwargs["output"] / "lane", allow_empty=True)
            self.assertEqual(temporary / "original", kwargs["output"])
            return {"originalProducer": self.producer}

        with mock.patch.object(sdk_apple_native.product_reuse, "paginated_items", return_value=[artifact]), \
                mock.patch.object(sdk_apple_native.tempfile, "TemporaryDirectory",
                                  return_value=nullcontext(str(alias))), \
                original_qualification_callable(qualify):
            sdk_apple_native._authenticate_native_transport_original(
                self.plan_path, receipt, self.producer, lane, self.lanes[lane],
                root=self.root, token=self.token, trusted_workflow_sha=self.pin)

    def test_malformed_transport_chain_and_cross_paired_proof_reject(self) -> None:
        lane = "ios-native-tests"
        receipt_path = self.lanes[lane] / "lane-receipt.json"
        receipt = json.loads(receipt_path.read_text())
        with mock.patch.dict(os.environ, self.environment, clear=False):
            lane_reuse.reissue_transport_receipt(
                self.lanes[lane], receipt, json.loads(self.plan_path.read_text()), lane,
                receipt["artifactName"],
            )
        provenance = self.lanes[lane] / "transport-provenance.json"
        valid_provenance = provenance.read_bytes()
        valid_receipt = receipt_path.read_bytes()
        value = json.loads(provenance.read_text())
        value["sourceTransportArtifactName"] = "codex-agent-ci-ios-native-tests-" + "f" * 40
        provenance.write_text(json.dumps(value, sort_keys=True) + "\n")
        updated = json.loads(receipt_path.read_text())
        next(item for item in updated["evidence"]
             if item["relativePath"] == provenance.name)["sha256"] = hashlib.sha256(provenance.read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(updated, sort_keys=True) + "\n")
        self._repack(lane)
        with self.assertRaisesRegex(ValueError, "wrong artifact identity"):
            context, _, patches = self.invoke()
            try:
                with context:
                    self.fail("malformed native transport provenance yielded inputs")
            finally:
                self.close(patches)
        provenance.write_bytes(valid_provenance)
        receipt_path.write_bytes(valid_receipt)
        self._repack(lane)

        lane = "ios-rust-simulator"
        proof_path = next(self.lanes[lane] / source for source, destination
                          in sdk_apple_native.NATIVE_FILES[lane].items() if destination.endswith(".json"))
        proof = self.proof("synthetic-simulator-proof", tree="f" * 40)
        proof_path.write_bytes(proof)
        receipt = json.loads((self.lanes[lane] / "lane-receipt.json").read_text())
        next(item for item in receipt["evidence"]
             if item["relativePath"] == proof_path.relative_to(self.lanes[lane]).as_posix())["sha256"] = hashlib.sha256(proof).hexdigest()
        (self.lanes[lane] / "lane-receipt.json").write_text(json.dumps(receipt, sort_keys=True) + "\n")
        self._repack(lane)
        with self.assertRaisesRegex(ValueError, "differs from its original producer"):
            context, _, patches = self.invoke()
            try:
                with context:
                    self.fail("cross-paired native proof yielded inputs")
            finally:
                self.close(patches)

    def _repack(self, lane: str) -> None:
        self.raw[lane] = archive_tree(self.lanes[lane])
        self.artifacts[lane]["digest"] = sha256_bytes(self.raw[lane])
        self.artifacts[lane]["size_in_bytes"] = len(self.raw[lane])

    def retain_native(self, destination, *, historical=False):
        receipt = self.original_binary_receipt()
        context, _, patches = self.invoke(original_binary_receipt_path=receipt if historical else None)
        try:
            with context as result:
                sdk_apple_native.snapshot_regular_tree(result["captureRoot"], destination, allow_empty=True)
        finally:
            self.close(patches)
        return receipt

    def test_retained_native_replays_fresh_and_historical_captures_without_network_or_rewriting(self):
        for historical in (False, True):
            captured = self.root / f"retained-{historical}"
            receipt = self.retain_native(captured, historical=historical)
            before = regular_file_inventory(captured, allow_empty=True)
            with self.subTest(historical=historical), \
                    mock.patch.object(sdk_apple_native.product_reuse, "_observe_ci_producer_jobs", side_effect=AssertionError("network")), \
                    mock.patch.object(sdk_apple_native.product_reuse, "_download_contract_ci_upload", side_effect=AssertionError("network")):
                with sdk_apple_native.verified_retained_sdk_apple_native_inputs(captured,
                        original_binary_receipt_path=receipt, repository_root=self.root) as result:
                    self.assertEqual(self.producer, result["producer"])
                    self.assertEqual(before, regular_file_inventory(result["captureRoot"], allow_empty=True))
                    self.assertEqual(sha256_bytes(receipt.read_bytes()), result["binaryReceiptSha256"])
                    self.assertEqual({lane: self.producer for lane in sdk_apple_native.LANES}, result["originalProducers"])
                    self.assertEqual((captured / "native-transport.json").read_bytes(),
                                     canonical_json_bytes(result["transport"]))
                self.assertFalse(result["captureRoot"].exists())
            self.assertEqual(before, regular_file_inventory(captured, allow_empty=True))

    def test_retained_native_archive_receipt_producer_and_extra_file_mutations_reject(self):
        original = self.root / "retained-baseline"
        receipt = self.retain_native(original)
        for index, mutation in enumerate(("archive", "lane", "flat", "receipt-digest", "producer", "extra-plan", "extra-root")):
            captured = self.root / f"retained-mutation-{index}"
            sdk_apple_native.snapshot_regular_tree(original, captured, allow_empty=True)
            lane = sdk_apple_native.LANES[0]
            if mutation == "archive":
                (captured / "archives" / f"{lane}.zip").write_bytes(b"changed archive")
            elif mutation == "lane":
                (captured / "lanes" / lane / "lane-result.txt").write_bytes(b"changed lane")
            elif mutation == "flat":
                (captured / "native-evidence/native-tests-proof.json").write_bytes(b"changed proof")
            elif mutation.startswith("extra"):
                (captured / ("plan/extra" if mutation == "extra-plan" else "extra")).write_bytes(b"extra")
            else:
                path = captured / "native-transport.json"
                value = json.loads(path.read_bytes())
                if mutation == "producer":
                    value["captureProducer"]["runAttempt"] += 1
                else:
                    value["receiptSha256s"][lane] = "sha256:" + "0" * 64
                path.write_bytes(canonical_json_bytes(value))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                with sdk_apple_native.verified_retained_sdk_apple_native_inputs(captured,
                        original_binary_receipt_path=receipt, repository_root=self.root):
                    self.fail("mutated native originals passed retained replay")

    def test_retained_native_context_exit_rejects_source_private_and_yielded_mutations(self):
        original = self.root / "retained-exit-baseline"
        receipt = self.retain_native(original)
        for index, mutation in enumerate(("source", "private", "evidence", "evidence-and-inventory", "producer", "transport", "receipt")):
            captured = self.root / f"retained-exit-{index}"
            sdk_apple_native.snapshot_regular_tree(original, captured, allow_empty=True)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "changed during use"):
                with sdk_apple_native.verified_retained_sdk_apple_native_inputs(captured,
                        original_binary_receipt_path=receipt, repository_root=self.root) as result:
                    if mutation == "producer":
                        result["originalProducers"][sdk_apple_native.LANES[0]]["runAttempt"] += 1
                    elif mutation == "transport":
                        result["transport"]["observed"] = []
                    elif mutation == "receipt":
                        result["receipts"][sdk_apple_native.LANES[0]]["runAttempt"] += 1
                    else:
                        directory = captured if mutation == "source" else result["captureRoot"] if mutation == "private" else result["directory"]
                        (directory / "unexpected.bin").write_bytes(b"changed")
                        if mutation == "evidence-and-inventory":
                            result["inventory"][:] = regular_file_inventory(directory)


if __name__ == "__main__":
    unittest.main()
