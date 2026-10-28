"""Transport tests for Apple source capture; the full source gate is tested separately."""

from __future__ import annotations

from argparse import Namespace
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock
import zipfile


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import receipt as lane_receipt  # noqa: E402
import reuse  # noqa: E402
import sdk_apple_source  # noqa: E402
from products.inventory import (  # noqa: E402
    load_canonical_json_bytes, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_bytes, write_canonical_json as actual_write_canonical_json,
)
from ci.tests import test_ci as ci_fixture  # noqa: E402
from ci.tests import test_sdk_apple_source as source_fixture  # noqa: E402


def _archive_tree(root: Path) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(value for value in root.rglob("*") if value.is_file()):
            archive.writestr(path.relative_to(root).as_posix(), path.read_bytes())
    return output.getvalue()


class SdkAppleSourceCaptureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = source_fixture.SdkAppleSourceTest(
            "test_real_git_lane_receipt_and_contract_projection_bind_exact_originals",
        )
        self.source.setUp()
        self.addCleanup(self.source.tearDown)
        self.addCleanup(self.source.doCleanups)
        self.root = self.source.root
        self.pin = "c" * 40
        self.output = self.root / "build/apple-source-capture"
        self.token = "not-a-real-token"
        self.environment = {"GITHUB_RUN_ID": "91", "GITHUB_RUN_ATTEMPT": "2"}

        self.upload_lane = self.root / "upload-lane"
        shutil.copytree(self.source.lane, self.upload_lane)
        (self.upload_lane / "lane-receipt.json").unlink()
        shutil.copytree(
            self.source.distribution,
            self.upload_lane / sdk_apple_source._DISTRIBUTION,
            dirs_exist_ok=True,
        )
        shutil.copytree(
            self.source.execution,
            self.upload_lane / sdk_apple_source._EXECUTION,
            dirs_exist_ok=True,
        )
        inventory_names = set(lane_receipt.INPUT_NAMES.values())
        evidence = [
            f"{path.relative_to(self.upload_lane).as_posix()}=synthetic-apple-observation"
            for path in sorted(value for value in self.upload_lane.rglob("*") if value.is_file())
            if path.name not in inventory_names
        ]
        lane_receipt.create_receipt(Namespace(
            plan=self.source.plan, lane="ios-swift-tests", output=self.upload_lane,
            workflow_path=".github/workflows/ci.yml",
            artifact_name=f"codex-agent-ci-ios-swift-tests-{self.source.tree}",
            run_id=91, run_attempt=2,
            runner=["os=macOS", "arch=ARM64"],
            toolchain=["xcode=26.3", "swift=6.2.3", "validationActions=build,metadata,test"],
            artifact=[], evidence=evidence,
        ))
        self.raw = _archive_tree(self.upload_lane)
        self.digest = sha256_bytes(self.raw)
        self.plan = json.loads(self.source.plan.read_text(encoding="utf-8"))
        self.artifact = {
            "id": 701,
            "name": f"codex-agent-ci-ios-swift-tests-{self.source.tree}",
            "size_in_bytes": len(self.raw),
            "digest": self.digest,
            "expired": False,
            "created_at": "2026-09-10T10:15:00Z",
            "archive_download_url":
                "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/701/zip",
            "workflow_run": {"id": 91, "head_sha": self.plan["headCommit"]},
        }

    def _run(self, run_id: int = 91, attempt: int = 2) -> dict[str, object]:
        return {
            "id": run_id,
            "run_attempt": attempt,
            "path": ".github/workflows/ci.yml",
            "head_sha": self.plan["headCommit"],
            "event": self.plan["event"],
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-09-10T10:00:00Z",
            "completed_at": "2026-09-10T10:30:00Z",
            "pull_requests": [{
                "number": self.plan["pullRequest"],
                "base": {"sha": self.plan["baseCommit"]},
                "head": {"sha": self.plan["headCommit"]},
            }],
            "repository": {"full_name": self.plan["repository"], "fork": False},
            "head_repository": {"full_name": self.plan["repository"], "fork": False},
            "referenced_workflows": [{
                "path": (f"{self.plan['repository']}/.github/workflows/"
                         f"product-validation.yml@{self.pin}"),
                "sha": self.pin,
            }],
        }

    def _commit(self) -> dict[str, object]:
        return {
            "sha": self.source.commit,
            "tree": {"sha": self.source.tree},
            "parents": [
                {"sha": self.plan["baseCommit"]},
                {"sha": self.plan["headCommit"]},
            ],
        }

    def _jobs(self, run_id: int = 91) -> list[dict[str, object]]:
        return [{
            "id": 801 + run_id,
            "name": sdk_apple_source._JOB,
            "run_id": run_id,
            "started_at": "2026-09-10T10:00:00Z",
            "completed_at": "2026-09-10T10:30:00Z",
            "head_sha": self.plan["headCommit"],
            "status": "completed",
            "conclusion": "success",
        }]

    def _api(self, *, artifact=None, raw=None, original_run: tuple[int, int] | None = None):
        selected_artifact = self.artifact if artifact is None else artifact
        selected_raw = self.raw if raw is None else raw
        attempts = {(91, 2)} | ({original_run} if original_run is not None else set())

        def request(url: str, token: str) -> bytes:
            self.assertEqual(self.token, token)
            for run_id, attempt in attempts:
                base = (f"https://api.github.com/repos/{self.plan['repository']}"
                        f"/actions/runs/{run_id}/attempts/{attempt}")
                if url == base:
                    return json.dumps(self._run(run_id, attempt)).encode()
                if url.startswith(base + "/jobs?"):
                    return json.dumps({"jobs": self._jobs(run_id)}).encode()
            if url == (f"https://api.github.com/repos/{self.plan['repository']}"
                       f"/git/commits/{self.source.commit}"):
                return json.dumps(self._commit()).encode()
            detail = (f"https://api.github.com/repos/{self.plan['repository']}"
                      f"/actions/artifacts/{selected_artifact['id']}")
            artifact_prefix = (f"https://api.github.com/repos/{self.plan['repository']}"
                               "/actions/artifacts/")
            if url == detail or (url.startswith(artifact_prefix)
                                 and url.removeprefix(artifact_prefix).isdigit()):
                return json.dumps(selected_artifact).encode()
            if url == selected_artifact["archive_download_url"]:
                return selected_raw
            raise AssertionError(f"Unexpected API request: {url}")

        return request

    def _gate(self, **arguments) -> None:
        lane = Path(arguments["ios_swift_tests_root"])
        self.assertNotEqual(self.upload_lane, lane)
        self.assertEqual(
            regular_file_inventory(self.upload_lane, allow_empty=True),
            regular_file_inventory(lane, allow_empty=True),
        )
        self.assertEqual(lane / sdk_apple_source._DISTRIBUTION,
                         Path(arguments["distribution_directory"]))
        self.assertEqual(lane / sdk_apple_source._EXECUTION,
                         Path(arguments["execution_directory"]))
        self.assertEqual(self.source.commit, arguments["expected_producer_commit"])
        self.assertEqual(self.source.tree, arguments["expected_producer_tree"])
        self.assertEqual(
            sha256_bytes((lane / "lane-receipt.json").read_bytes()),
            arguments["expected_lane_receipt_sha256"],
        )

    def _capture(self, *, gate=None, artifact=None, raw=None, original_run=None, api=None, **changes):
        arguments = {
            "plan_path": self.source.plan,
            "destination": self.output,
            "artifact_id": self.artifact["id"],
            "artifact_sha256": self.digest,
            "trusted_workflow_sha": self.pin,
            "contract_bundle": self.source.contract_bundle,
            "contract_projection": self.source.projection,
            "expected_distribution_proof": self.source.expected_proof,
            "expected_sdk_compatibility": self.source.expected_compatibility,
            "tooling_evidence": self.source.tooling_evidence,
            "tooling_public_key": self.source.tooling_public_key,
            "java_executable": self.source.java_executable,
            "policy_revision": self.source.commit,
            "required_trust_domain": "development",
            "repository_root": self.root,
            "environ": self.environment,
            "token": self.token,
        }
        request = api or self._api(artifact=artifact, raw=raw, original_run=original_run)
        with mock.patch("reuse.api_request", side_effect=request), mock.patch(
            "sdk_apple_source.verify_sdk_apple_original_source",
            side_effect=gate or self._gate,
        ):
            return sdk_apple_source.capture_sdk_apple_original_ci(**{**arguments, **changes})

    def test_captures_exact_upload_and_invokes_existing_gate_on_private_inputs(self) -> None:
        before = regular_file_inventory(self.upload_lane, allow_empty=True)
        evidence = self._capture()
        self.assertEqual(before, regular_file_inventory(self.upload_lane, allow_empty=True))
        self.assertEqual(before, regular_file_inventory(self.output / "lane", allow_empty=True))
        self.assertEqual(self.raw, (self.output / "transport/upload.zip").read_bytes())
        retained = load_canonical_json_bytes(
            (self.output / "transport/original-apple-ci.json").read_bytes(),
        )
        self.assertEqual(evidence, retained)
        self.assertEqual(self.artifact, retained["artifact"])
        self.assertEqual(retained["captureProducer"], retained["originalProducer"])
        self.assertEqual(retained["observed"], retained["originalObserved"])
        self.assertEqual(b"", (self.output / "lane" / sdk_apple_source._EXECUTION
                              / "compiler-raw/operation/stderr.bin").read_bytes())

    def test_transport_identity_archive_and_full_gate_fail_without_publication(self) -> None:
        cases = (
            ("id", {"artifact_id": 702}, None, None, "transport identity"),
            ("digest", {"artifact_sha256": sha256_bytes(b"wrong")}, None, None,
             "transport identity"),
            ("name", {}, {**self.artifact, "name": "wrong"}, None, "transport identity"),
            ("stale", {}, {**self.artifact, "created_at": "2026-09-10T09:59:59Z"},
             None, "job-attempt window"),
            ("missing timestamp", {}, {**self.artifact, "created_at": None}, None,
             "timestamp"),
            ("bytes", {}, None, self.raw + b"changed", "digest"),
        )
        for label, changes, artifact, raw, message in cases:
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, message):
                self._capture(artifact=artifact, raw=raw, **changes)
            self.assertFalse(self.output.exists())
        with self.assertRaisesRegex(ValueError, "existing full gate rejected"):
            self._capture(gate=ValueError("existing full gate rejected"))
        self.assertFalse(self.output.exists())

        unsafe = io.BytesIO()
        with zipfile.ZipFile(unsafe, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("../escape", b"unsafe")
        unsafe_raw = unsafe.getvalue()
        unsafe_digest = sha256_bytes(unsafe_raw)
        unsafe_artifact = {
            **self.artifact,
            "size_in_bytes": len(unsafe_raw),
            "digest": unsafe_digest,
        }
        with self.assertRaises(ValueError):
            self._capture(
                artifact=unsafe_artifact, raw=unsafe_raw,
                artifact_sha256=unsafe_digest,
            )
        self.assertFalse(self.output.exists())
        self.assertFalse((self.root / "escape").exists())

        def mutate_private_lane(**arguments) -> None:
            (Path(arguments["ios_swift_tests_root"]) / "lane-receipt.json").write_bytes(b"changed")

        with self.assertRaisesRegex(ValueError, "changed during verification"):
            self._capture(gate=mutate_private_lane)
        self.assertFalse(self.output.exists())

    def test_pre_pin_and_late_transport_mutations_do_not_publish(self) -> None:
        extract = sdk_apple_source.safe_extract

        def mutate_extracted_lane(archive, destination):
            result = extract(archive, destination)
            if Path(destination).name == "lane":
                (Path(destination) / "lane-receipt.json").write_bytes(b"changed extraction")
            return result

        with mock.patch.object(sdk_apple_source, "safe_extract",
                               side_effect=mutate_extracted_lane), \
                self.assertRaisesRegex(ValueError, "extraction differs from authenticated upload"):
            self._capture()
        self.assertFalse(self.output.exists())

        def mutate_before_pin(path, value):
            actual_write_canonical_json(path, value)
            (Path(path).parent / "upload.zip").write_bytes(b"changed before pin")

        with mock.patch.object(sdk_apple_source, "write_canonical_json",
                               side_effect=mutate_before_pin), \
                self.assertRaisesRegex(ValueError, "changed before publication"):
            self._capture()
        self.assertFalse(self.output.exists())

        def mutate_before_copy(source, destination, **kwargs):
            (Path(source) / "transport/original-apple-ci.json").write_bytes(
                b"changed after pin")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch.object(sdk_apple_source, "publish_regular_tree",
                               side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self._capture()
        self.assertFalse(self.output.exists())

    def test_same_commit_original_receipt_attempt_is_observed_separately(self) -> None:
        lane_receipt.create_receipt(Namespace(
            plan=self.source.plan, lane="ios-swift-tests", output=self.upload_lane,
            workflow_path=".github/workflows/ci.yml",
            artifact_name=f"codex-agent-ci-ios-swift-tests-{self.source.tree}",
            run_id=81, run_attempt=1,
            runner=["os=macOS", "arch=ARM64"],
            toolchain=["xcode=26.3", "swift=6.2.3", "validationActions=build,metadata,test"],
            artifact=[], evidence=[
                f"{path.relative_to(self.upload_lane).as_posix()}=synthetic-apple-observation"
                for path in sorted(value for value in self.upload_lane.rglob("*") if value.is_file())
                if path.name not in {"lane-receipt.json", *lane_receipt.INPUT_NAMES.values()}
            ],
        ))
        self.raw = _archive_tree(self.upload_lane)
        self.digest = sha256_bytes(self.raw)
        self.artifact = {**self.artifact, "size_in_bytes": len(self.raw), "digest": self.digest}
        evidence = self._capture(original_run=(81, 1))
        self.assertEqual(91, evidence["captureProducer"]["runId"])
        self.assertEqual(81, evidence["originalProducer"]["runId"])
        self.assertEqual([91], [value["run"]["id"] for value in evidence["observed"]])
        self.assertEqual([81], [value["run"]["id"] for value in evidence["originalObserved"]])

    def test_cross_commit_transport_replays_authenticated_original_plan_and_lane(self) -> None:
        original_plan = json.loads(self.source.plan.read_text(encoding="utf-8"))
        original_plan_root = self.root / "original-plan-upload"
        (original_plan_root / "inventories").mkdir(parents=True)
        shutil.copy2(self.source.plan, original_plan_root / "impact-plan.json")
        shutil.copytree(
            self.source.plan.parent / "inventories",
            original_plan_root / "inventories", dirs_exist_ok=True,
        )
        original_plan_raw = _archive_tree(original_plan_root)
        lane_receipt.create_receipt(Namespace(
            plan=original_plan_root / "impact-plan.json", lane="ios-swift-tests",
            output=self.upload_lane, workflow_path=".github/workflows/ci.yml",
            artifact_name=f"codex-agent-ci-ios-swift-tests-{self.source.tree}",
            run_id=81, run_attempt=1,
            runner=["os=macOS", "arch=ARM64"],
            toolchain=["xcode=26.3", "swift=6.2.3", "validationActions=build,metadata,test"],
            artifact=[], evidence=[
                f"{path.relative_to(self.upload_lane).as_posix()}=synthetic-apple-observation"
                for path in sorted(value for value in self.upload_lane.rglob("*") if value.is_file())
                if path.name not in {"lane-receipt.json", *lane_receipt.INPUT_NAMES.values()}
            ],
        ))
        original_lane = self.root / "original-lane-upload"
        shutil.copytree(self.upload_lane, original_lane)
        original_lane_raw = _archive_tree(original_lane)

        current_commit = ci_fixture.GitFixture.commit(
            self.source, "current-only/change.txt", "changed\n",
        )
        current_plan_path = self.source.plan
        current_plan = ci_fixture.plan(
            root=self.root, base=self.source.base, target=current_commit, head=current_commit,
            event="pull_request", pull_request=7, force_full=True,
            require_android_evidence=False, repository="codex-agent-labs/codex-agent",
            output=current_plan_path,
            **self.source.pull_request_authorization(
                base=self.source.base, target=current_commit, pull_request=7,
            ),
        )
        current_tree = self.source.git("rev-parse", f"{current_commit}^{{tree}}")
        current_lane = self.root / "current-lane-upload"
        shutil.copytree(original_lane, current_lane)
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "91", "GITHUB_RUN_ATTEMPT": "2"}):
            reuse.reissue_transport_receipt(
                current_lane,
                json.loads((current_lane / "lane-receipt.json").read_text(encoding="utf-8")),
                current_plan,
                "ios-swift-tests",
                f"codex-agent-ci-ios-swift-tests-{self.source.tree}",
            )
        current_raw = _archive_tree(current_lane)
        current_digest = sha256_bytes(current_raw)
        current_artifact = {
            **self.artifact,
            "name": f"codex-agent-ci-ios-swift-tests-{current_tree}",
            "size_in_bytes": len(current_raw),
            "digest": current_digest,
            "workflow_run": {"id": 91, "head_sha": current_plan["headCommit"]},
        }
        original_artifacts = ({
            "id": 702,
            "name": f"codex-agent-ci-ios-swift-tests-{self.source.tree}",
            "size_in_bytes": len(original_lane_raw),
            "digest": sha256_bytes(original_lane_raw),
            "expired": False,
            "created_at": "2026-09-10T10:15:00Z",
            "archive_download_url":
                "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/702/zip",
            "workflow_run": {"id": 81, "head_sha": original_plan["headCommit"]},
        }, {
            "id": 703,
            "name": f"codex-agent-ci-plan-{self.source.tree}",
            "size_in_bytes": len(original_plan_raw),
            "digest": sha256_bytes(original_plan_raw),
            "expired": False,
            "created_at": "2026-09-10T10:05:00Z",
            "archive_download_url":
                "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/703/zip",
            "workflow_run": {"id": 81, "head_sha": original_plan["headCommit"]},
        })
        runs = {
            91: {**self._run(), "head_sha": current_plan["headCommit"], "pull_requests": [{
                "number": current_plan["pullRequest"],
                "base": {"sha": current_plan["baseCommit"]},
                "head": {"sha": current_plan["headCommit"]},
            }]},
            81: {**self._run(81, 1), "head_sha": original_plan["headCommit"]},
        }
        commits = {
            current_commit: {
                "sha": current_commit, "tree": {"sha": current_tree}, "parents": [
                    {"sha": current_plan["baseCommit"]}, {"sha": current_plan["headCommit"]},
                ],
            },
            self.source.commit: self._commit(),
        }
        jobs = {
            91: [{**value, "head_sha": current_plan["headCommit"]}
                 for value in self._jobs(91)],
            81: [*self._jobs(81), {
                "id": 982,
                "name": sdk_apple_source._PLAN_JOB,
                "run_id": 81,
                "head_sha": original_plan["headCommit"],
                "status": "completed", "conclusion": "success",
                "started_at": "2026-09-10T10:00:00Z",
                "completed_at": "2026-09-10T10:10:00Z",
            }],
        }
        archives = {
            current_artifact["archive_download_url"]: current_raw,
            original_artifacts[0]["archive_download_url"]: original_lane_raw,
            original_artifacts[1]["archive_download_url"]: original_plan_raw,
        }
        details = {value["id"]: value for value in (current_artifact, *original_artifacts)}

        def api(url: str, token: str) -> bytes:
            self.assertEqual(self.token, token)
            for run_id, run in runs.items():
                base = (f"https://api.github.com/repos/{self.plan['repository']}"
                        f"/actions/runs/{run_id}/attempts/{run['run_attempt']}")
                if url == base:
                    return json.dumps(run).encode()
                if url.startswith(base + "/jobs?"):
                    return json.dumps({"jobs": jobs[run_id]}).encode()
            commit_prefix = (f"https://api.github.com/repos/{self.plan['repository']}"
                             "/git/commits/")
            if url.startswith(commit_prefix):
                return json.dumps(commits[url.removeprefix(commit_prefix)]).encode()
            artifacts_url = (f"https://api.github.com/repos/{self.plan['repository']}"
                             "/actions/runs/81/artifacts")
            if url.startswith(artifacts_url + "?"):
                return json.dumps({"artifacts": list(original_artifacts)}).encode()
            detail_prefix = (f"https://api.github.com/repos/{self.plan['repository']}"
                             "/actions/artifacts/")
            if url.startswith(detail_prefix) and url.removeprefix(detail_prefix).isdigit():
                return json.dumps(details[int(url.removeprefix(detail_prefix))]).encode()
            if url in archives:
                return archives[url]
            raise AssertionError(f"Unexpected API request: {url}")

        def gate(**arguments) -> None:
            repository = Path(arguments["repository"])
            self.assertNotEqual(self.root, repository)
            self.assertEqual(self.source.commit, subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repository, check=True,
                capture_output=True, text=True,
            ).stdout.strip())
            self.assertEqual(
                regular_file_inventory(original_lane, allow_empty=True),
                regular_file_inventory(Path(arguments["ios_swift_tests_root"]), allow_empty=True),
            )
            self.assertEqual(
                (original_plan_root / "impact-plan.json").read_bytes(),
                Path(arguments["impact_plan"]).read_bytes(),
            )
            self.assertEqual(self.source.commit, arguments["expected_producer_commit"])
            self.assertEqual(self.source.tree, arguments["expected_producer_tree"])

        self.plan = current_plan
        self.artifact = current_artifact
        self.raw = current_raw
        self.digest = current_digest
        self.environment = {"GITHUB_RUN_ID": "91", "GITHUB_RUN_ATTEMPT": "2"}
        original_lane_before = regular_file_inventory(original_lane, allow_empty=True)
        original_plan_before = regular_file_inventory(original_plan_root, allow_empty=True)
        for label, mutate in (
            ("lane", lambda arguments: (
                Path(arguments["ios_swift_tests_root"]) / "lane-receipt.json"
            ).write_bytes(b"changed private original lane\n")),
            ("plan", lambda arguments: Path(arguments["impact_plan"]).write_bytes(
                b"changed private original plan\n",
            )),
        ):
            with self.subTest(private_mutation=label), self.assertRaisesRegex(
                ValueError, "original plan changed during verification|source lane or original plan changed",
            ):
                self._capture(gate=lambda **arguments: mutate(arguments), api=api)
            self.assertFalse(self.output.exists())
            self.assertEqual(
                original_lane_before, regular_file_inventory(original_lane, allow_empty=True),
            )
            self.assertEqual(
                original_plan_before, regular_file_inventory(original_plan_root, allow_empty=True),
            )

        def mutate_original_zip_before_copy(source, destination, **kwargs):
            (Path(source) / "transport/original-lane-upload.zip").write_bytes(
                b"changed original upload after pin")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch.object(sdk_apple_source, "publish_regular_tree",
                               side_effect=mutate_original_zip_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self._capture(api=api, gate=gate)
        self.assertFalse(self.output.exists())
        evidence = self._capture(api=api, gate=gate)
        self.assertEqual(self.source.commit, evidence["originalProducer"]["commit"])
        self.assertEqual(
            regular_file_inventory(original_lane, allow_empty=True),
            regular_file_inventory(self.output / "lane", allow_empty=True),
        )
        self.assertEqual(current_raw, (self.output / "transport/upload.zip").read_bytes())
        self.assertEqual(
            original_lane_raw, (self.output / "transport/original-lane-upload.zip").read_bytes(),
        )
        self.assertEqual(
            original_plan_raw, (self.output / "transport/original-plan-upload.zip").read_bytes(),
        )
        self.assertEqual(
            regular_file_inventory(current_lane, allow_empty=True),
            regular_file_inventory(self.output / "transport/current-lane", allow_empty=True),
        )

    def test_input_alias_rejects_before_network_and_preserves_the_input(self) -> None:
        original = self.source.plan.read_bytes()
        with mock.patch("reuse.api_request") as request, self.assertRaises(ValueError):
            sdk_apple_source.capture_sdk_apple_original_ci(
                self.source.plan, self.source.plan,
                artifact_id=self.artifact["id"], artifact_sha256=self.digest,
                trusted_workflow_sha=self.pin, contract_bundle=self.source.contract_bundle,
                contract_projection=self.source.projection,
                expected_distribution_proof=self.source.expected_proof,
                expected_sdk_compatibility=self.source.expected_compatibility,
                tooling_evidence=self.source.tooling_evidence,
                tooling_public_key=self.source.tooling_public_key,
                java_executable=self.source.java_executable,
                policy_revision=self.source.commit, required_trust_domain="development",
                repository_root=self.root, environ=self.environment, token=self.token,
            )
        request.assert_not_called()
        self.assertEqual(original, self.source.plan.read_bytes())

        policy = self.root / "caller-policy"
        keys = policy / "keys"
        keys.mkdir(parents=True)
        keyring = policy / "keyring.json"
        keyring.write_bytes(b"caller policy\n")
        nested = keys / "capture"
        with mock.patch("reuse.api_request") as request, self.assertRaisesRegex(
            ValueError, "overlaps an input",
        ):
            self._capture(
                destination=nested, tooling_keyring=keyring, tooling_keys_directory=keys,
            )
        request.assert_not_called()
        self.assertFalse(nested.exists())
        self.assertEqual(b"caller policy\n", keyring.read_bytes())

        self.output.mkdir()
        with mock.patch("reuse.api_request") as request, self.assertRaisesRegex(
            ValueError, "must not exist",
        ):
            self._capture()
        request.assert_not_called()
        self.assertTrue(self.output.is_dir())
        self.assertEqual([], list(self.output.iterdir()))

        absent = self.root / "build/no-token-output"
        with mock.patch("reuse.api_request") as request, self.assertRaisesRegex(
            ValueError, "requires an observation token",
        ):
            self._capture(destination=absent, token="")
        request.assert_not_called()
        self.assertFalse(absent.exists())


if __name__ == "__main__":
    unittest.main()
