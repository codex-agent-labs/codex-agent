"""Offline stop-gates for SDK candidate's official promoted catalog custody."""

from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from ci import sdk_candidate_catalog as candidate
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file


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


if __name__ == "__main__":
    unittest.main()
