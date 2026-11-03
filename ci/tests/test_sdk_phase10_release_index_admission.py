"""No-secret SDK later-record custody; mocked API is not hosted acceptance."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from ci import sdk_phase10_release_index_admission as admission
from ci.products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file,
)


class SdkPhase10ReleaseIndexAdmissionTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.destination = self.root / "capture"
        self.original = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40,
            "tree": "b" * 40, "event": "pull_request", "runId": 41,
            "runAttempt": 2, "pullRequest": 31}
        self.record = {**self.original, "commit": "c" * 40,
            "tree": "d" * 40, "event": "workflow_dispatch", "runId": 88,
            "runAttempt": 1, "pullRequest": None}
        self.authority_dispatch = {**self.record, "runId": 77}
        self.authority_dispatch_file = self.root / "authority-producer.json"
        self.authority_dispatch_file.write_bytes(
            canonical_json_bytes(self.authority_dispatch))
        self.index = b'{"signed":"index"}\n'
        self.signature = b"SSHSIG signed bytes\n"
        (self.root / "keyring.json").write_bytes(b"keyring")
        keys = self.root / "keys"
        keys.mkdir()
        (keys / "release-test.pub").write_bytes(b"public key")
        self.keys_inventory_sha256 = sha256_bytes(canonical_json_bytes(
            admission.regular_file_inventory(keys)))
        self.archive = self.root / "upload.zip"
        with ZipFile(self.archive, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr("product-index.json", self.index)
            zipped.writestr("product-index.sig", self.signature)
        self.options = dict(
            original_producer=self.original,
            expected_original_producer_sha256=sha256_bytes(canonical_json_bytes(self.original)),
            record_producer=self.record,
            expected_record_producer_sha256=sha256_bytes(canonical_json_bytes(self.record)),
            record_artifact_id=17, record_artifact_sha256=sha256_file(self.archive),
            trusted_record_workflow_sha="e" * 40,
            expected_index_sha256=sha256_bytes(self.index),
            expected_signature_sha256=sha256_bytes(self.signature),
            keyring_path=self.root / "keyring.json",
            keys_directory=self.root / "keys",
            expected_keyring_sha256=sha256_bytes(b"keyring"),
            expected_keys_inventory_sha256=self.keys_inventory_sha256,
            authority_file=self.root / "authority.json",
            expected_authority_sha256=sha256_bytes(b"authority"),
            authority_producer=self.authority_dispatch,
            expected_authority_producer_sha256=sha256_file(
                self.authority_dispatch_file),
            token="observation-only", environ={},
        )

    def capture(self, **changes):
        authority_catalog_producer = changes.pop("authority_catalog_producer", self.original)
        mutate_keys = changes.pop("mutate_keys", False)
        options = {**self.options, **changes}
        seen = []
        self.events = seen

        @contextmanager
        def authority(*_args, **_kwargs):
            yield {"completedCatalogPin": {"producer": authority_catalog_producer}}

        def observe(producers, *, jobs_by_phase, trusted_workflows_by_phase,
                    dispatch_authorization_job, allow_protected_dispatch, **_kwargs):
            self.assertEqual({"record": self.record}, producers)
            self.assertEqual({"record": admission._JOB}, jobs_by_phase)
            self.assertEqual(admission._WORKFLOW,
                trusted_workflows_by_phase["record"]["path"])
            self.assertIsNone(dispatch_authorization_job)
            self.assertTrue(allow_protected_dispatch)
            seen.append("observe")
            return [{"run": {"status": "completed", "conclusion": "success",
                              "head_sha": self.record["commit"]}, "jobs": []}]

        def download(_id, _digest, name, producer, _run, _token, *, destination,
                     max_bytes):
            self.assertEqual(self.record, producer)
            self.assertEqual(20 * 1024 * 1024, max_bytes)
            self.assertEqual(
                "codex-agent-sdk-phase10-release-index-" + self.original["tree"] +
                "-attestation-88-attempt-1", name)
            destination.write_bytes(self.archive.read_bytes())
            seen.append("download")
            return {"id": 17, "digest": sha256_file(self.archive)}, destination

        def replay(signed, _plan, _repository, **kwargs):
            self.assertEqual(self.index, signed.manifest.read_bytes())
            self.assertEqual(self.signature, signed.signature.read_bytes())
            self.assertEqual(self.original, kwargs["producer"])
            self.assertEqual((41, 2), (kwargs["original_run_id"],
                                        kwargs["original_run_attempt"]))
            evidence = kwargs["evidence_destination"]
            evidence.mkdir()
            for member in admission._EVIDENCE_MEMBERS:
                (evidence / member).write_bytes(
                    b"keyring" if member == "product-signing-keys.json"
                    else member.encode())
            (evidence / "keys").mkdir()
            (evidence / "keys/release-test.pub").write_bytes(b"public key")
            if mutate_keys:
                (self.root / "keys/release-test.pub").write_bytes(b"changed key")
            seen.append("replay")
            return {"entries": ["verified"]}, self.index

        with (patch.object(admission, "_release_key"),
              patch.object(admission, "held_pinned_sdk_campaign_authority",
                           side_effect=authority),
              patch.object(admission.products, "_observe_ci_producer_jobs",
                           side_effect=observe) as official,
              patch.object(admission.products, "_download_contract_ci_upload",
                           side_effect=download),
              patch.object(admission.products, "_require_artifact_job_window"),
              patch.object(admission, "verify_signed_sdk_release_index_against_official_replay",
                           side_effect=replay)):
            result = admission.capture_signed_sdk_phase10_index(
                self.root / "plan.json", self.root, self.destination, **options)
        return result, seen, official

    def test_distinct_pinned_dispatch_retains_exact_signed_pair_and_upload(self):
        result, seen, official = self.capture()
        self.assertEqual(["observe", "download", "replay"], seen)
        official.assert_called_once()
        self.assertEqual(sha256_file(self.archive),
            sha256_file(self.destination / "official-upload.zip"))
        self.assertEqual(self.index,
            (self.destination / "signed-pair/product-index.json").read_bytes())
        self.assertEqual(self.signature,
            (self.destination / "signed-pair/product-index.sig").read_bytes())
        self.assertEqual(admission._EVIDENCE_MEMBERS,
            {path.name for path in (self.destination / "replay-evidence").iterdir()
             if path.is_file()})
        self.assertTrue((self.destination /
            "replay-evidence/keys/release-test.pub").is_file())
        self.assertEqual(self.options["expected_index_sha256"], result["indexSha256"])

    def test_wrong_independent_producer_pin_rejects_before_observation(self):
        with self.assertRaisesRegex(ValueError, "independently approved pins"):
            self.capture(expected_record_producer_sha256=sha256_bytes(b"wrong"))
        self.assertEqual([], self.events)
        self.assertFalse(self.destination.exists())

    def test_context_override_and_wrong_signed_bytes_reject(self):
        with self.assertRaisesRegex(ValueError, "cannot replace"):
            self.capture(producer=self.record)
        with self.assertRaisesRegex(ValueError, "originals changed before capture"):
            self.capture(expected_index_sha256=sha256_bytes(b"wrong"))
        self.assertFalse(self.destination.exists())

    def test_original_campaign_pin_and_distinct_dispatch_are_required(self):
        with self.assertRaisesRegex(ValueError, "protected campaign authority"):
            self.capture(authority_catalog_producer={**self.original, "runId": 42})
        self.assertEqual([], self.events)
        with self.assertRaisesRegex(ValueError, "distinct approved PR and dispatch"):
            self.capture(record_producer={**self.record, "runId": 41},
                expected_record_producer_sha256=sha256_bytes(canonical_json_bytes(
                    {**self.record, "runId": 41})))
        with self.assertRaisesRegex(ValueError, "independently pinned and distinct"):
            self.capture(authority_producer={**self.authority_dispatch, "runId": 88},
                expected_authority_producer_sha256=sha256_bytes(canonical_json_bytes(
                    {**self.authority_dispatch, "runId": 88})))
        self.assertEqual([], self.events)

    def test_fixed_child_workflow_and_job_must_be_officially_observed(self):
        run = {"id": 88, "run_attempt": 1,
               "path": ".github/workflows/ci.yml", "event": "workflow_dispatch",
               "status": "completed", "conclusion": "success",
               "head_sha": self.record["commit"],
               "repository": {"full_name": self.record["repository"], "fork": False},
               "head_repository": {"full_name": self.record["repository"], "fork": False},
               "referenced_workflows": [{"path":
                   self.record["repository"] + "/" + admission._WORKFLOW + "@" + "e" * 40,
                   "sha": "e" * 40}]}
        job = {"id": 91, "run_id": 88, "head_sha": self.record["commit"],
               "name": admission._JOB, "status": "completed", "conclusion": "success"}
        request = dict(producers={"record": self.record},
            jobs_by_phase={"record": admission._JOB},
            trusted_workflows_by_phase={"record": {
                "path": admission._WORKFLOW, "sha": "e" * 40}},
            token="observation-only", allow_protected_dispatch=True,
            dispatch_authorization_job=None)
        with patch.object(admission.products, "api_json", return_value=run), \
             patch.object(admission.products, "_observe_tested_commit", return_value={}), \
             patch.object(admission.products, "paginated_items", return_value=[job]):
            self.assertEqual(1, len(admission.products._observe_ci_producer_jobs(**request)))
        wrong_workflow = {**run, "referenced_workflows": [{**run["referenced_workflows"][0],
            "path": self.record["repository"] + "/.github/workflows/other.yml@" + "e" * 40}]}
        with patch.object(admission.products, "api_json", return_value=wrong_workflow), \
             patch.object(admission.products, "_observe_tested_commit", return_value={}), \
             patch.object(admission.products, "paginated_items", return_value=[job]), \
             self.assertRaisesRegex(ValueError, "caller-pinned workflow"):
            admission.products._observe_ci_producer_jobs(**request)
        with patch.object(admission.products, "api_json", return_value=run), \
             patch.object(admission.products, "_observe_tested_commit", return_value={}), \
             patch.object(admission.products, "paginated_items", return_value=[
                 {**job, "name": "sdk-phase10-record / wrong-child"}]), \
             self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            admission.products._observe_ci_producer_jobs(**request)

    def test_unexpected_zip_member_rejects_before_full_replay(self):
        extra = self.root / "extra.zip"
        with ZipFile(extra, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr("product-index.json", self.index)
            zipped.writestr("product-index.sig", self.signature)
            zipped.writestr("unreviewed.txt", b"extra")
        self.archive = extra
        with self.assertRaises(ValueError):
            self.capture(record_artifact_sha256=sha256_file(extra))
        self.assertEqual(["observe", "download"], self.events)
        self.assertFalse(self.destination.exists())

    def test_public_key_mutation_before_atomic_capture_rejects(self):
        with self.assertRaisesRegex(ValueError, "originals changed before capture"):
            self.capture(mutate_keys=True)
        self.assertFalse(self.destination.exists())

    def test_cli_forwards_explicit_pins_and_existing_replay_options(self):
        original_path = self.root / "original-producer.json"
        record_path = self.root / "record-producer.json"
        original_path.write_bytes(canonical_json_bytes(self.original))
        record_path.write_bytes(canonical_json_bytes(self.record))
        args = ["--plan", str(self.root / "plan.json"),
            "--repository-root", str(self.root),
            "--authority-file", str(self.root / "authority.json"),
            "--authority-producer", str(self.authority_dispatch_file),
            "--expected-authority-producer-sha256", sha256_file(
                self.authority_dispatch_file),
            "--keyring-path", str(self.root / "keyring.json"),
            "--keys-directory", str(self.root / "keys"),
            "--expected-keys-inventory-sha256", self.keys_inventory_sha256,
            "--authority-artifact-id", "9", "--state-artifact-id", "8",
            "--state-wave", "0", "--authority-artifact-sha256", sha256_bytes(b"authority"),
            "--authority-workflow-sha", "e" * 40,
            "--authority-workflow-path", ".github/workflows/sdk-phase10-later-authority.yml",
            "--authority-job-name", "sdk-phase10-authority / sdk-phase10-authority",
            "--trusted-workflow-sha", "e" * 40,
            "--state-artifact-sha256", sha256_bytes(b"state"),
            "--destination", str(self.destination),
            "--original-producer", str(original_path),
            "--expected-original-producer-sha256", sha256_file(original_path),
            "--record-producer", str(record_path),
            "--expected-record-producer-sha256", sha256_file(record_path),
            "--record-artifact-id", "17",
            "--record-artifact-sha256", sha256_file(self.archive),
            "--trusted-record-workflow-sha", "e" * 40,
            "--expected-index-sha256", sha256_bytes(self.index),
            "--expected-signature-sha256", sha256_bytes(self.signature)]
        for family in ("core-android", "native", "apple-js"):
            for kind in ("election", "semantic"):
                args += [f"--{kind}-{family}", str(self.root / f"{kind}-{family}.json")]

        @contextmanager
        def options(_args):
            yield {"producer": self.original, "repository": self.original["repository"],
                "context": {"kind": "pull-request"},
                "original_run_id": None, "original_run_attempt": None,
                "token": "observation-only", "environ": {},
                "keyring_path": self.root / "keyring.json",
                "keys_directory": self.root / "keys",
                "expected_keyring_sha256": sha256_bytes(b"keyring"),
                "expected_keys_inventory_sha256": self.keys_inventory_sha256,
                "authority_file": self.root / "authority.json",
                "authority_producer": self.authority_dispatch,
                "expected_authority_producer_sha256": sha256_file(
                    self.authority_dispatch_file)}

        approved = {"CODEX_AGENT_SDK_INDEX_APPROVED_SHA256": sha256_bytes(self.index),
            "CODEX_AGENT_SDK_SIGNATURE_APPROVED_SHA256": sha256_bytes(self.signature)}
        def captured(_plan, _root, private, **_kwargs):
            private.mkdir()
            (private / "product-index.json").write_bytes(self.index)
            return {"artifactId": 17, "artifactSha256": sha256_file(self.archive),
                "indexSha256": sha256_bytes(self.index),
                "signatureSha256": sha256_bytes(self.signature),
                "files": regular_file_inventory(private)}
        with patch.dict(os.environ, approved, clear=True), \
             patch.object(admission, "held_sdk_release_replay_options",
                          side_effect=options), \
             patch.object(admission, "capture_signed_sdk_phase10_index",
                          side_effect=captured) as capture, \
             redirect_stdout(StringIO()):
            self.assertEqual(0, admission.main(args))
        self.assertEqual(self.index, (self.destination / "product-index.json").read_bytes())
        self.assertNotEqual(self.destination, capture.call_args.args[2])
        self.assertEqual(self.original, capture.call_args.kwargs["original_producer"])
        self.assertEqual(self.record, capture.call_args.kwargs["record_producer"])
        self.assertEqual(17, capture.call_args.kwargs["record_artifact_id"])
        args[args.index("--expected-record-producer-sha256") + 1] = sha256_bytes(b"wrong")
        with patch.dict(os.environ, approved, clear=True), \
             patch.object(admission, "held_sdk_release_replay_options") as selected, \
             patch.object(admission, "capture_signed_sdk_phase10_index") as capture, \
             redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            admission.main(args)
        selected.assert_not_called()
        capture.assert_not_called()

    def test_cli_late_held_failure_leaves_no_published_destination(self):
        original_path = self.root / "original-producer.json"
        record_path = self.root / "record-producer.json"
        original_path.write_bytes(canonical_json_bytes(self.original))
        record_path.write_bytes(canonical_json_bytes(self.record))
        destination = self.root / "late-capture"
        args = ["--plan", str(self.root / "plan.json"),
            "--repository-root", str(self.root),
            "--authority-file", str(self.root / "authority.json"),
            "--authority-producer", str(self.authority_dispatch_file),
            "--expected-authority-producer-sha256", sha256_file(self.authority_dispatch_file),
            "--keyring-path", str(self.root / "keyring.json"),
            "--keys-directory", str(self.root / "keys"),
            "--expected-keys-inventory-sha256", self.keys_inventory_sha256,
            "--authority-artifact-id", "9", "--state-artifact-id", "8",
            "--state-wave", "0", "--authority-artifact-sha256", sha256_bytes(b"authority"),
            "--authority-workflow-sha", "e" * 40,
            "--authority-workflow-path", ".github/workflows/sdk-phase10-later-authority.yml",
            "--authority-job-name", "sdk-phase10-authority / sdk-phase10-authority",
            "--trusted-workflow-sha", "e" * 40,
            "--state-artifact-sha256", sha256_bytes(b"state"),
            "--destination", str(destination),
            "--original-producer", str(original_path),
            "--expected-original-producer-sha256", sha256_file(original_path),
            "--record-producer", str(record_path),
            "--expected-record-producer-sha256", sha256_file(record_path),
            "--record-artifact-id", "17", "--record-artifact-sha256", sha256_file(self.archive),
            "--trusted-record-workflow-sha", "e" * 40,
            "--expected-index-sha256", sha256_bytes(self.index),
            "--expected-signature-sha256", sha256_bytes(self.signature)]
        for family in ("core-android", "native", "apple-js"):
            for kind in ("election", "semantic"):
                args += [f"--{kind}-{family}", str(self.root / f"{kind}-{family}.json")]
        selected = {"producer": self.original, "repository": self.original["repository"],
            "context": {"kind": "pull-request"},
            "original_run_id": None, "original_run_attempt": None,
            "token": "observation-only", "environ": {},
            "keyring_path": self.root / "keyring.json", "keys_directory": self.root / "keys",
            "expected_keyring_sha256": sha256_bytes(b"keyring"),
            "expected_keys_inventory_sha256": self.keys_inventory_sha256,
            "authority_file": self.root / "authority.json",
            "authority_producer": self.authority_dispatch,
            "expected_authority_producer_sha256": sha256_file(self.authority_dispatch_file)}

        @contextmanager
        def late_failure(_args):
            yield selected
            raise ValueError("held policy changed after capture")

        def captured(_plan, _root, private, **_kwargs):
            private.mkdir()
            (private / "product-index.json").write_bytes(self.index)
            return {"files": regular_file_inventory(private)}

        approved = {"CODEX_AGENT_SDK_INDEX_APPROVED_SHA256": sha256_bytes(self.index),
            "CODEX_AGENT_SDK_SIGNATURE_APPROVED_SHA256": sha256_bytes(self.signature)}
        with patch.dict(os.environ, approved, clear=True), \
             patch.object(admission, "held_sdk_release_replay_options",
                          side_effect=late_failure), \
             patch.object(admission, "capture_signed_sdk_phase10_index",
                          side_effect=captured), \
             redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            admission.main(args)
        self.assertFalse(destination.exists())

        @contextmanager
        def no_late_failure(_args):
            yield selected

        def mutate_producer(*capture_args, **capture_kwargs):
            result = captured(*capture_args, **capture_kwargs)
            record_path.write_bytes(canonical_json_bytes({**self.record, "runId": 89}))
            return result

        args[args.index("--destination") + 1] = str(self.root / "late-producer")
        with patch.dict(os.environ, approved, clear=True), \
             patch.object(admission, "held_sdk_release_replay_options",
                          side_effect=no_late_failure), \
             patch.object(admission, "capture_signed_sdk_phase10_index",
                          side_effect=mutate_producer), \
             redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            admission.main(args)
        self.assertFalse((self.root / "late-producer").exists())


if __name__ == "__main__":
    unittest.main()
