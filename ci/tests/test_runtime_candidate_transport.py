"""Runtime candidate transport is pinned custody, never admission."""

from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from ci import runtime_candidate_transport as candidate
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file


_A, _B, _C = "a" * 40, "b" * 40, "c" * 40
_D = "sha256:" + "d" * 64


def _temporary():
    # The macOS system temp path traverses /var -> /private/var; safe-file
    # readers intentionally reject that symlink ancestry.
    return tempfile.TemporaryDirectory(prefix="runtime-candidate-test-", dir=Path.cwd())


def _producer(event, run, *, commit=_A, tree=_B):
    return {"repository": candidate._REPOSITORY,
            "workflowPath": ".github/workflows/promote.yml" if event == "push"
                            else ".github/workflows/ci.yml",
            "event": event, "commit": commit, "tree": tree,
            "pullRequest": 31 if event == "pull_request" else None,
            "runId": run, "runAttempt": 1}


def _selection():
    return {"schemaVersion": 1,
            "catalog": {"producer": _producer("push", 10),
                        "trustedWorkflowSha": _C, "artifactId": 30,
                        "artifactSha256": _D, "inventorySha256": _D,
                        "indexSha256": _D, "signatureSha256": _D},
            "phase10": {"originalProducer": _producer("merge_group", 11),
                        "recordProducer": _producer("workflow_dispatch", 12),
                        "trustedRecordWorkflowSha": _C, "artifactId": 31,
                        "artifactSha256": _D, "recordSha256": _D,
                        "signatureSha256": _D}}


def _archive(path, members):
    with ZipFile(path, "w") as zipped:
        for name, content in members.items():
            zipped.writestr(name, content)


class RuntimeCandidateTransportTest(unittest.TestCase):
    def test_selection_rejects_wrong_tree_route_and_unpinned_artifact(self):
        value = _selection()
        value["catalog"]["producer"]["tree"] = _C
        with self.assertRaisesRegex(ValueError, "distinct promoted/Phase-10 originals"):
            candidate.validate_selection(value)
        value = _selection()
        value["phase10"]["recordProducer"]["event"] = "pull_request"
        with self.assertRaisesRegex(ValueError, "pullRequest"):
            candidate.validate_selection(value)
        value = _selection()
        value["phase10"]["originalProducer"]["event"] = "pull_request"
        value["phase10"]["originalProducer"]["pullRequest"] = 31
        with self.assertRaisesRegex(ValueError, "distinct promoted/Phase-10 originals"):
            candidate.validate_selection(value)
        value = _selection()
        value["catalog"]["artifactSha256"] = "not-a-digest"
        with self.assertRaisesRegex(ValueError, "sha256:"):
            candidate.validate_selection(value)

    def test_cli_rejects_unapproved_selection_before_observation(self):
        with _temporary() as temporary:
            root = Path(temporary)
            source = root / "selection.json"
            source.write_bytes(canonical_json_bytes(_selection()))
            with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}), \
                    patch.object(candidate, "capture_runtime_candidate_transports") as capture, \
                    self.assertRaisesRegex(ValueError, "differs from S1048 pin"):
                candidate.main(["--selection", str(source),
                    "--expected-selection-sha256", _D,
                    "--destination", str(root / "out")])
            capture.assert_not_called()

    def test_catalog_observer_requires_successful_exact_main_child_and_tree(self):
        producer = _producer("push", 10)
        run = {"id": 10, "run_attempt": 1, "path": ".github/workflows/promote.yml",
               "event": "push", "head_branch": "main", "head_sha": _A,
               "status": "completed", "conclusion": "success",
               "referenced_workflows": [{"path": (
                   f"{candidate._REPOSITORY}/{candidate._CATALOG_WORKFLOW}@{_C}"),
                   "sha": _C}],
               "repository": {"full_name": candidate._REPOSITORY, "fork": False},
               "head_repository": {"full_name": candidate._REPOSITORY, "fork": False}}
        commit = {"sha": _A, "tree": {"sha": _B}}
        job = {"name": candidate._CATALOG_JOB, "id": 50, "run_id": 10,
               "head_sha": _A, "status": "completed", "conclusion": "success"}
        def api(url, token):
            self.assertEqual(token, "token")
            return commit if "/git/commits/" in url else run
        with patch.object(candidate.transport, "api_json", side_effect=api), \
                patch.object(candidate.transport, "paginated_items", return_value=[job]):
            self.assertEqual(candidate._observe_catalog(producer, _C, "token")["run"], run)
            run["referenced_workflows"][0]["sha"] = _A
            with self.assertRaisesRegex(ValueError, "caller-pinned workflow"):
                candidate._observe_catalog(producer, _C, "token")
            run["referenced_workflows"][0]["sha"] = _C
            commit["tree"]["sha"] = _C
            with self.assertRaisesRegex(ValueError, "differs from selected tree"):
                candidate._observe_catalog(producer, _C, "token")

    def test_retains_pinned_official_zips_without_admitting_candidate(self):
        with _temporary() as temporary:
            root = Path(temporary)
            catalog_source = root / "catalog-source"
            (catalog_source / "catalog").mkdir(parents=True)
            (catalog_source / "caller.json").write_bytes(b"{}\n")
            (catalog_source / "catalog/product-index.json").write_bytes(b"index\n")
            (catalog_source / "catalog/product-index.sig").write_bytes(b"signature\n")
            (catalog_source / "trust").mkdir()
            (catalog_source / "trust/public.pub").write_bytes(b"public\n")
            catalog_archive = root / "catalog.zip"
            _archive(catalog_archive, {file.relative_to(catalog_source).as_posix(): file.read_bytes()
                                       for file in catalog_source.rglob("*") if file.is_file()})
            record_archive = root / "record.zip"
            _archive(record_archive, {"record.json": b"record\n", "record.sig": b"sig\n"})
            selected = _selection()
            selected["catalog"].update({
                "artifactSha256": sha256_file(catalog_archive),
                "inventorySha256": sha256_bytes(canonical_json_bytes(
                    regular_file_inventory(catalog_source))),
                "indexSha256": sha256_file(catalog_source / "catalog/product-index.json"),
                "signatureSha256": sha256_file(catalog_source / "catalog/product-index.sig"),
            })
            selected["phase10"].update({
                "artifactSha256": sha256_file(record_archive),
                "recordSha256": sha256_bytes(b"record\n"),
                "signatureSha256": sha256_bytes(b"sig\n"),
            })
            sources = {30: catalog_archive, 31: record_archive}
            def download(artifact_id, digest, name, producer, observed_run, token, *, destination):
                self.assertEqual(digest, sha256_file(sources[artifact_id]))
                self.assertEqual(observed_run["id"], producer["runId"])
                shutil.copyfile(sources[artifact_id], destination)
                return {"id": artifact_id, "name": name, "digest": digest}, destination
            def observed(producer, *args, **kwargs):
                return {"run": {"id": producer["runId"]}, "jobs": []}
            with patch.object(candidate, "_observe_catalog", side_effect=observed), \
                    patch.object(candidate, "_observe_protected_record_dispatch", side_effect=observed), \
                    patch.object(candidate.transport, "_download_contract_ci_upload", side_effect=download), \
                    patch.object(candidate.transport, "_require_artifact_job_window"):
                retained = root / "retained"
                result = candidate.capture_runtime_candidate_transports(
                    selected, retained, token="token", environ={})
                self.assertIs(result["admitted"], False)
                self.assertEqual(sha256_file(retained / "catalog.zip"), selected["catalog"]["artifactSha256"])
                self.assertEqual(sha256_file(retained / "phase10-record.zip"),
                                 selected["phase10"]["artifactSha256"])
                self.assertEqual(result["files"], regular_file_inventory(retained))
                bad = copy.deepcopy(selected)
                bad["phase10"]["signatureSha256"] = _D
                with self.assertRaisesRegex(ValueError, "record differs"):
                    candidate.capture_runtime_candidate_transports(
                        bad, root / "rejected", token="token", environ={})
                self.assertFalse((root / "rejected").exists())
                bad = copy.deepcopy(selected)
                bad["catalog"]["signatureSha256"] = _D
                with self.assertRaisesRegex(ValueError, "catalog bytes differ"):
                    candidate.capture_runtime_candidate_transports(
                        bad, root / "rejected-signature", token="token", environ={})
                self.assertFalse((root / "rejected-signature").exists())

    def test_capture_rejects_any_signing_secret_even_empty(self):
        with patch.object(candidate, "_observe_catalog") as observe, \
                self.assertRaisesRegex(ValueError, "signing secrets"):
            candidate.capture_runtime_candidate_transports(
                _selection(), Path("unused"), token="token",
                environ={"SIGNING_IN_MEMORY_KEY": ""})
        observe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
