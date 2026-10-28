"""Offline stop-gates for SDK candidate's official promoted catalog custody."""

from __future__ import annotations

import copy
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from ci import sdk_candidate_catalog as candidate
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file
from ci.products.registry import PHASE_INSTANCE_IDS
from ci.products.runtime_library_authorization import _LIBRARY_PATHS
from ci.tests.test_sdk_candidate_semantics import _parity_fixture
from ci.tests.test_sdk_completion import phase


_A, _B, _C = "a" * 40, "b" * 40, "c" * 40
_D = "sha256:" + "1" * 64


def _selection() -> dict:
    return {"schemaVersion": 1,
            "producer": {"repository": candidate._REPOSITORY,
                         "workflowPath": ".github/workflows/promote.yml",
                         "event": "push", "commit": _A, "tree": _B,
                         "pullRequest": None, "runId": 10, "runAttempt": 1},
            "trustedWorkflowSha": _C, "artifactId": 20,
            "artifactSha256": _D, "inventorySha256": _D,
            "indexSha256": _D, "signatureSha256": _D}


class SdkCandidateCatalogTest(unittest.TestCase):
    def test_selection_rejects_missing_and_unreviewed_fields(self):
        selected = _selection()
        candidate._selection(selected)
        for change in ({"trustedWorkflowSha": "main"},
                       {"artifactId": True}, {"signatureSha256": "bad"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                candidate._selection({**selected, **change})
        for field in ("signatureSha256", "artifactId"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                candidate._selection({key: value for key, value in selected.items() if key != field})
        with self.assertRaises(ValueError):
            candidate._selection({**selected, "extra": 1})

    def test_observer_requires_exact_successful_main_and_child_workflow(self):
        producer = _selection()["producer"]
        run = {"id": 10, "run_attempt": 1, "path": producer["workflowPath"],
               "event": "push", "head_branch": "main", "head_sha": _A,
               "status": "completed", "conclusion": "success",
               "referenced_workflows": [{"path":
                   f"{candidate._REPOSITORY}/{candidate._WORKFLOW}@{_C}", "sha": _C}],
               "repository": {"full_name": candidate._REPOSITORY, "fork": False},
               "head_repository": {"full_name": candidate._REPOSITORY, "fork": False}}
        job = {"id": 22, "run_id": 10, "head_sha": _A, "name": candidate._JOB,
               "status": "completed", "conclusion": "success"}
        commit = {"sha": _A, "tree": {"sha": _B}}

        def api(url, _token):
            return commit if "/git/commits/" in url else run

        with patch.object(candidate.transport, "api_json", side_effect=api), \
             patch.object(candidate.transport, "paginated_items", return_value=[job]):
            self.assertEqual(candidate._observe(producer, _C, "token")["run"], run)
            for change in ({"head_branch": "other"}, {"conclusion": "failure"},
                           {"head_sha": _C}, {"repository": {"full_name":
                               candidate._REPOSITORY, "fork": True}}):
                with self.subTest(change=change), patch.dict(run, change), \
                     self.assertRaises(ValueError):
                    candidate._observe(producer, _C, "token")
            with patch.dict(run["referenced_workflows"][0], {"sha": _A}), \
                 self.assertRaisesRegex(ValueError, "caller-pinned workflow"):
                candidate._observe(producer, _C, "token")
            with patch.dict(job, {"name": "unrelated"}), \
                 self.assertRaisesRegex(ValueError, "sign job"):
                candidate._observe(producer, _C, "token")

    def test_cli_requires_independent_selection_digest_before_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / "selection.json"
            path.write_bytes(canonical_json_bytes(_selection()))
            with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}), \
                 patch.object(candidate, "capture_sdk_candidate_catalog") as capture, \
                 self.assertRaisesRegex(ValueError, "protected S1048 digest"):
                candidate.main(["--selection", str(path),
                                "--expected-selection-sha256", _D,
                                "--destination", str(root / "out")])
            capture.assert_not_called()

    def test_exact_official_zip_inventory_is_retained_without_transport_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root / "source.zip"
            with ZipFile(archive, "w") as output:
                output.writestr("product-index.json", "{}\n")
                output.writestr("product-index.sig", "signature\n")
                output.writestr("objects/one.zip", b"bytes")
            extracted = root / "fixture"
            candidate.safe_extract(archive, extracted)
            files = regular_file_inventory(extracted)
            selected = _selection()
            selected.update({"artifactSha256": sha256_file(archive),
                             "inventorySha256": sha256_bytes(canonical_json_bytes(files)),
                             "indexSha256": sha256_file(extracted / "product-index.json"),
                             "signatureSha256": sha256_file(extracted / "product-index.sig")})
            artifact = {"id": 20, "created_at": "2026-09-28T10:02:00Z"}
            observed = {"run": {}, "jobs": [{"name": candidate._JOB,
                         "started_at": "2026-09-28T10:01:00Z",
                         "completed_at": "2026-09-28T10:03:00Z"}]}

            def download(*_args, destination, **_kwargs):
                shutil.copyfile(archive, destination)
                return artifact, destination

            with patch.object(candidate, "_observe", return_value=observed), \
                 patch.object(candidate.transport, "_download_contract_ci_upload",
                              side_effect=download):
                destination = root / "out"
                result = candidate.capture_sdk_candidate_catalog(
                    selected, destination, token="token", environ={})
                self.assertEqual(result["artifactSha256"], selected["artifactSha256"])
                self.assertEqual(regular_file_inventory(destination), files)
                self.assertFalse((destination / "official-upload.zip").exists())
                tampered = copy.deepcopy(selected)
                tampered["inventorySha256"] = _D
                with self.assertRaisesRegex(ValueError, "independent S1048 pins"):
                    candidate.capture_sdk_candidate_catalog(
                        tampered, root / "rejected", token="token", environ={})
                self.assertFalse((root / "rejected").exists())
            with patch.object(candidate, "_observe") as observer, \
                 self.assertRaises(ValueError):
                candidate.capture_sdk_candidate_catalog(
                    selected, root / "secret", token="token",
                    environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "private"})
            observer.assert_not_called()


class SdkCandidateParityTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.archive, self.phases = _parity_fixture(self.root, [phase(item) for item in sorted(PHASE_INSTANCE_IDS)])
        self.selected = dict(schemaVersion=1, producer=dict(repository=candidate._REPOSITORY,
            workflowPath=".github/workflows/ci.yml", event="pull_request", pullRequest=31,
            commit=_A, tree=_B, runId=10, runAttempt=1), trustedWorkflowSha=_C, jobId=22,
            artifactId=20, artifactSha256=sha256_file(self.archive), artifactBytes=self.archive.stat().st_size,
            phaseIdentitiesSha256=sha256_file(self.phases))
        self.run = dict(id=10, run_attempt=1, path=".github/workflows/ci.yml", event="pull_request",
            status="completed", conclusion="failure", head_sha=_A, pull_requests=[{"number": 31}],
            referenced_workflows=[dict(path=f"{candidate._REPOSITORY}/{candidate._PARITY_WORKFLOW}@{_C}", sha=_C)],
            repository=dict(full_name=candidate._REPOSITORY, fork=False),
            head_repository=dict(full_name=candidate._REPOSITORY, fork=False))
        self.job = dict(id=22, run_id=10, head_sha=_A, name=candidate._PARITY_JOB,
            status="completed", conclusion="success", started_at="2026-10-20T12:00:00Z",
            completed_at="2026-10-20T13:00:00Z")
        self.artifact = dict(id=20, digest=self.selected["artifactSha256"], expired=False,
            name="codex-agent-sdk-binding-parity-" + _B,
            archive_download_url=f"https://api.github.com/repos/{candidate._REPOSITORY}/actions/artifacts/20/zip",
            workflow_run=dict(id=10, head_sha=_A), size_in_bytes=self.selected["artifactBytes"],
            created_at="2026-10-20T12:30:00Z")
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(patch.object(candidate.transport, "_original_ci_run", return_value=self.run))
        self.stack.enter_context(patch.object(candidate.transport, "_observe_tested_commit",
            return_value=dict(sha=_A, tree=dict(sha=_B))))
        self.jobs = self.stack.enter_context(patch.object(candidate.transport, "paginated_items", return_value=[self.job]))
        self.metadata = self.stack.enter_context(patch.object(candidate.transport, "api_json", return_value=self.artifact))
        self.acquire = self.stack.enter_context(patch.object(candidate.transport, "_reuse_contract_ci_upload",
            side_effect=AssertionError("held archive must not download")))
        self.extract = self.stack.enter_context(patch.object(candidate, "safe_extract",
            side_effect=AssertionError("parity capture must not extract the full archive")))

    def capture(self, name="out", **kwargs):
        return candidate.capture_sdk_candidate_parity(self.selected, self.archive, self.root / name,
                                                       token="observation-only", environ={}, **kwargs)

    def test_held_success_survives_failed_parent_and_keeps_original_bytes_without_copy(self):
        before = self.archive.stat()
        result = self.capture()
        self.assertFalse(result["admitted"])
        self.assertTrue(result["heldArchive"])
        self.assertEqual(self.archive.stat(), before)
        self.assertEqual(self.phases.read_bytes(), (self.root / "out/original-phase-identities.json").read_bytes())
        self.assertEqual({"transport.json", "original-phase-identities.json"},
                         {item.name for item in (self.root / "out").iterdir()})
        record = json.loads((self.root / "out/transport.json").read_bytes())
        self.assertEqual(self.selected["producer"], record["producer"])
        self.assertEqual([self.job], record["observed"]["jobs"])
        self.capture("second")
        self.assertEqual(2, self.metadata.call_count)  # fresh custody on each call
        self.assertEqual(2, self.jobs.call_count)
        self.acquire.assert_not_called()
        self.extract.assert_not_called()

    def test_missing_archive_downloads_once_after_metadata_and_window_admission(self):
        destination = self.root / "missing.zip"
        def acquire(*args, **kwargs):
            self.assertEqual(1, self.metadata.call_count)
            self.assertEqual(self.artifact, args[0])
            self.assertEqual(candidate._PARITY_LIMIT, kwargs["limit"])
            shutil.copyfile(self.archive, kwargs["destination"])
        self.acquire.side_effect = acquire
        result = candidate.capture_sdk_candidate_parity(self.selected, destination, self.root / "out",
                                                       token="observation-only", environ={})
        self.assertFalse(result["heldArchive"])
        self.assertEqual(self.selected["artifactSha256"], sha256_file(destination))
        self.acquire.assert_called_once()
        self.metadata.assert_called_once()
        self.extract.assert_not_called()

    def test_invalid_source_job_window_size_and_phase_pins_fail_without_download(self):
        mutations = [(self.run, {"event": "push"}), (self.run, {"head_repository": {"fork": True}}),
            (self.run["referenced_workflows"][0], {"sha": _A}), (self.job, {"conclusion": "failure"}),
            (self.job, {"id": 23}), (self.artifact, {"created_at": "2026-10-21T12:30:00Z"}),
            (self.artifact, {"digest": _D}), (self.artifact, {"expired": True}),
            (self.artifact, {"size_in_bytes": self.selected["artifactBytes"] + 1}),
            (self.selected, {"phaseIdentitiesSha256": _D})]
        for target, change in mutations:
            with self.subTest(change=change), patch.dict(target, change), self.assertRaises(ValueError):
                self.capture()
            self.assertFalse((self.root / "out").exists())
        self.acquire.assert_not_called()

    def test_corrupt_held_original_and_signing_secrets_never_trigger_replacement(self):
        self.archive.write_bytes(b"corrupt original retained for diagnosis")
        with self.assertRaises(ValueError):
            self.capture()
        self.assertEqual(b"corrupt original retained for diagnosis", self.archive.read_bytes())
        self.acquire.assert_not_called()
        self.metadata.reset_mock()
        for name in (*candidate._SECRETS, "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"):
            with patch.dict(os.environ, {name: "forbidden"}), self.assertRaisesRegex(ValueError, "secret"):
                self.capture()
        self.metadata.assert_not_called()
        path = self.root / "selection.json"
        path.write_bytes(canonical_json_bytes(self.selected))
        with self.assertRaisesRegex(ValueError, "S1048 digest"):
            candidate.main(["--kind", "parity", "--archive", str(self.archive),
                "--selection", str(path), "--expected-selection-sha256", _D,
                "--destination", str(self.root / "cli")])
        self.metadata.assert_not_called()


class SdkCandidateRuntimeCustodyTest(unittest.TestCase):
    """Local transport fixtures only; no Runtime signing or release admission."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.archive = self.root / "libraries.zip"
        self.members = {target + "/" + Path(path).name: (target + " fixture library").encode()
                        for target, path in _LIBRARY_PATHS.items()}
        with ZipFile(self.archive, "w") as zipped:
            for path, raw in sorted(self.members.items()):
                zipped.writestr(path, raw)
        files = [dict(relativePath=path, bytes=len(raw), sha256=sha256_bytes(raw))
                 for path, raw in sorted(self.members.items())]
        self.selected = dict(schemaVersion=1, producer=dict(repository=candidate._REPOSITORY,
            workflowPath=".github/workflows/ci.yml", event="workflow_dispatch", pullRequest=None,
            commit=_A, tree=_B, runId=10, runAttempt=1), trustedWorkflowSha=_C, jobId=22,
            artifactId=20, artifactSha256=sha256_file(self.archive), artifactBytes=self.archive.stat().st_size,
            validationCommit="d" * 40, inventorySha256=sha256_bytes(canonical_json_bytes(files)))
        self.run = dict(id=10, run_attempt=1, path=".github/workflows/ci.yml", event="workflow_dispatch",
            status="completed", conclusion="success", head_sha=_A, pull_requests=[],
            referenced_workflows=[dict(path=f"{candidate._REPOSITORY}/{candidate._RUNTIME_WORKFLOW}@{_C}", sha=_C)],
            repository=dict(full_name=candidate._REPOSITORY, fork=False),
            head_repository=dict(full_name=candidate._REPOSITORY, fork=False))
        self.job = dict(id=22, run_id=10, head_sha=_A, name=candidate._RUNTIME_JOB,
            status="completed", conclusion="success", started_at="2026-10-20T12:00:00Z",
            completed_at="2026-10-20T13:00:00Z")
        self.artifact = dict(id=20, digest=self.selected["artifactSha256"], expired=False,
            name="codex-agent-runtime-library-authorizations-" + "d" * 40 + "-attestation-10-attempt-1",
            archive_download_url=f"https://api.github.com/repos/{candidate._REPOSITORY}/actions/artifacts/20/zip",
            workflow_run=dict(id=10, head_sha=_A), size_in_bytes=self.selected["artifactBytes"],
            created_at="2026-10-20T12:30:00Z")
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(patch.object(candidate.transport, "_original_ci_run", return_value=self.run))
        self.stack.enter_context(patch.object(candidate.transport, "_observe_tested_commit",
            return_value=dict(sha=_A, tree=dict(sha=_B))))
        self.jobs = self.stack.enter_context(patch.object(candidate.transport, "paginated_items", return_value=[self.job]))
        self.metadata = self.stack.enter_context(patch.object(candidate.transport, "api_json", return_value=self.artifact))
        self.acquire = self.stack.enter_context(patch.object(candidate.transport, "_reuse_contract_ci_upload",
            side_effect=AssertionError("held original must not download")))
        self.extract = self.stack.enter_context(patch.object(candidate, "safe_extract",
            side_effect=AssertionError("custody must not extract/copy library trees")))

    def capture(self, name="out", archive=None):
        return candidate.capture_sdk_candidate_runtime(self.selected, archive or self.archive,
            self.root / name, token="fixture-observation-only", environ={})

    def test_held_upload_keeps_original_and_publishes_only_small_controls(self):
        before = self.archive.stat()
        result = self.capture()
        self.assertFalse(result["admitted"])
        self.assertTrue(result["heldArchive"])
        self.assertEqual(before, self.archive.stat())
        self.assertEqual({"transport.json", "library-inventory.json"},
                         {path.name for path in (self.root / "out").iterdir()})
        self.assertEqual(self.selected["inventorySha256"], sha256_file(self.root / "out/library-inventory.json"))
        record = json.loads((self.root / "out/transport.json").read_bytes())
        self.assertEqual(self.selected["producer"], record["producer"])
        self.assertEqual([self.job], record["observed"]["jobs"])
        self.capture("second")
        self.assertEqual(2, self.metadata.call_count)
        self.assertEqual(2, self.jobs.call_count)  # fresh provenance, not serialized trust
        self.acquire.assert_not_called()
        self.extract.assert_not_called()

    def test_missing_upload_downloads_once_after_exact_full_job_and_window(self):
        def acquire(*args, **kwargs):
            self.assertEqual(1, self.metadata.call_count)
            self.assertEqual(self.artifact, args[0])
            self.assertEqual(candidate._RUNTIME_LIMIT, kwargs["limit"])
            shutil.copyfile(self.archive, kwargs["destination"])
        self.acquire.side_effect = acquire
        downloaded = self.root / "downloaded.zip"
        result = self.capture(archive=downloaded)
        self.assertFalse(result["heldArchive"])
        self.assertEqual(self.selected["artifactSha256"], sha256_file(downloaded))
        self.acquire.assert_called_once()
        self.metadata.assert_called_once()
        self.extract.assert_not_called()

    def test_validation_job_failed_run_changed_pins_and_originals_reject(self):
        mutations = [(self.run, {"event": "pull_request"}), (self.run, {"conclusion": "failure"}),
            (self.run["referenced_workflows"][0], {"sha": _A}),
            (self.job, {"name": "sdk-runtime-library-validation / runtime-library-release-authorizations"}),
            (self.job, {"conclusion": "failure"}), (self.job, {"id": 23}),
            (self.artifact, {"created_at": "2026-10-21T12:30:00Z"}),
            (self.artifact, {"size_in_bytes": self.selected["artifactBytes"] + 1}),
            (self.artifact, {"digest": _D}), (self.artifact, {"expired": True}),
            (self.selected, {"inventorySha256": _D}), (self.selected, {"validationCommit": _A}),
            (self.selected, {"artifactBytes": candidate._RUNTIME_LIMIT + 1})]
        for target, change in mutations:
            with self.subTest(change=change), patch.dict(target, change), self.assertRaises(ValueError):
                self.capture()
            self.assertFalse((self.root / "out").exists())
        self.archive.write_bytes(b"corrupt original remains available for diagnosis")
        with self.assertRaises(ValueError):
            self.capture()
        self.assertEqual(b"corrupt original remains available for diagnosis", self.archive.read_bytes())
        self.acquire.assert_not_called()

    def test_sidecars_only_extra_roots_and_late_mutation_never_publish(self):
        def replace(members):
            with ZipFile(self.archive, "w") as zipped:
                for path, raw in sorted(members.items()):
                    zipped.writestr(path, raw)
            files = [dict(relativePath=path, bytes=len(raw), sha256=sha256_bytes(raw))
                     for path, raw in sorted(members.items())]
            self.selected.update(artifactSha256=sha256_file(self.archive), artifactBytes=self.archive.stat().st_size,
                                 inventorySha256=sha256_bytes(canonical_json_bytes(files)))
            self.artifact.update(digest=self.selected["artifactSha256"], size_in_bytes=self.selected["artifactBytes"])
        for members in ({path + ".evidence/claim.json": raw for path, raw in self.members.items()},
                        {**self.members, "unrelated/extra": b"extra"}):
            replace(members)
            with self.assertRaisesRegex(ValueError, "full five-library"):
                self.capture()
        replace(self.members)
        writer = candidate.write_canonical_json
        def mutate(path, value):
            writer(path, value)
            if path.name == "transport.json":
                self.archive.write_bytes(b"changed after scan")
        with patch.object(candidate, "write_canonical_json", side_effect=mutate), \
             self.assertRaisesRegex(ValueError, "inputs changed"):
            self.capture()
        self.assertFalse((self.root / "out").exists())
        self.metadata.reset_mock()
        for key in (*candidate._SECRETS, "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"):
            with patch.dict(os.environ, {key: "forbidden"}), self.assertRaisesRegex(ValueError, "secret"):
                self.capture()
        self.metadata.assert_not_called()


if __name__ == "__main__":
    unittest.main()
