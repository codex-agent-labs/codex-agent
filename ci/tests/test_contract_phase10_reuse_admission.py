from contextlib import redirect_stdout
from io import StringIO
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from ci import contract_phase10_reuse_admission as admission
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, sha256_file,
)


class ContractPhase10ReuseAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ct-reuse-admission-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.validation = self.root / "validation"
        self.trusted = self.root / "trusted"
        self.validation.mkdir()
        self.trusted.mkdir()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"original plan\n")
        self.destination = self.root / "captured"
        self.producer = {
            "repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 41, "runAttempt": 2, "pullRequest": 31,
        }
        self.archives = {}
        for kind, files in {"output": {"maven/primary.jar": b"primary"},
                            "record": {"record.json": b"signed record\n",
                                       "record.sig": b"signature\n"}}.items():
            archive = self.root / f"{kind}.zip"
            with ZipFile(archive, "w", ZIP_DEFLATED) as zipped:
                for name, contents in files.items():
                    zipped.writestr(name, contents)
            self.archives[kind] = archive

    def invoke(self, *, record_id=18, output_id=17, producer=None, recorded_producer=None,
               record_producer=None, record_workflow_sha=None,
               record_job_name="product-validation / contract-phase10-output-record / contract-phase10-record",
               mutate_snapshot=False):
        seen = []
        original_snapshot = admission.snapshot_regular_tree

        def snapshot(source, destination):
            original_snapshot(source, destination)
            if mutate_snapshot and destination.name == "output":
                (destination / "maven/primary.jar").write_bytes(b"altered after verification")

        def download(artifact_id, digest, name, original, run, token, *, destination):
            kind = "output" if artifact_id == 17 else "record"
            seen.append((artifact_id, digest, name, original))
            destination.write_bytes(self.archives[kind].read_bytes())
            return {"id": artifact_id, "digest": digest, "name": name}, destination

        def verify(record, signature, _trusted, _validation, output, _plan, **pins):
            self.assertEqual(b"signed record\n", record.read_bytes())
            self.assertEqual(b"signature\n", signature.read_bytes())
            self.assertEqual(b"primary", (output / "maven/primary.jar").read_bytes())
            self.assertEqual(17, pins["artifact_id"])
            return {"officialUpload": {"producer": recorded_producer or self.producer},
                    "outputFiles": regular_file_inventory(output)}

        def observe(_producers, *, jobs_by_phase, trusted_workflows_by_phase, **_ignored):
            self.assertEqual({"output"} if record_producer else {"output", "record"},
                             set(jobs_by_phase))
            self.assertEqual({".github/workflows/contract-phase10-output-record.yml"},
                             {route["path"] for route in trusted_workflows_by_phase.values()})
            if not record_producer and jobs_by_phase["record"] != (
                    "product-validation / contract-phase10-output-record / contract-phase10-record"):
                raise ValueError("Contract original producer job is missing or ambiguous")
            return [{"run": {"head_sha": "a" * 40}, "jobs": []}]

        with (patch.object(admission.products, "_validate_plan", return_value={
                "remoteBuildAuthorized": True, "event": "pull_request"}),
              patch.object(admission.products, "_consumer", return_value={
                  "producer": self.producer}),
              patch.object(admission.products, "_observe_ci_producer_jobs", side_effect=observe) as observed,
              patch.object(admission, "_observe_protected_record_dispatch", return_value={
                  "run": {"head_sha": record_producer["commit"] if record_producer else "a" * 40},
                  "jobs": [],
              }) as dispatched,
              patch.object(admission.products, "_download_contract_ci_upload", side_effect=download),
              patch.object(admission.products, "_require_artifact_job_window") as window,
              patch.object(admission, "verify_signed_contract_phase10_output_record", side_effect=verify),
              patch.object(admission, "snapshot_regular_tree", side_effect=snapshot)):
            result = admission.capture_reusable_contract_phase10_output(
                self.plan, self.validation, self.trusted, self.destination,
                original_producer=producer or self.producer,
                record_producer=record_producer,
                trusted_source_commit="c" * 40, trusted_workflow_sha="c" * 40,
                trusted_workflow_path=".github/workflows/contract-phase10-output-record.yml",
                output_job_name="product-validation / contract-phase10-output-record / contract-phase10-output",
                record_job_name=record_job_name,
                trusted_record_workflow_sha=record_workflow_sha,
                expected_pgp_key_sha256="sha256:" + "d" * 64,
                output_artifact_id=output_id,
                output_artifact_sha256=sha256_file(self.archives["output"]),
                record_artifact_id=record_id,
                record_artifact_sha256=sha256_file(self.archives["record"]),
                token="fixture-token", environ={},
            )
        return result, seen, observed, window, dispatched

    def test_two_independently_pinned_official_uploads_are_retained(self):
        result, seen, observe, window, dispatch = self.invoke()
        self.assertEqual([17, 18], [item[0] for item in seen])
        self.assertIn("codex-agent-contract-phase10-maven-", seen[0][2])
        self.assertIn("codex-agent-contract-phase10-output-record-", seen[1][2])
        self.assertEqual(self.producer, result["producer"])
        self.assertEqual(b"primary", (self.destination / "output/maven/primary.jar").read_bytes())
        self.assertEqual(b"signature\n", (self.destination / "signed-record/record.sig").read_bytes())
        transport = load_canonical_json_bytes((self.destination / "transport.json").read_bytes())
        self.assertEqual(self.producer, transport["producer"])
        self.assertEqual({"output": 17, "record": 18},
                         {kind: upload["id"] for kind, upload in transport["officialUploads"].items()})
        self.assertEqual("a" * 40, transport["observedAttempt"]["run"]["head_sha"])
        self.assertEqual(2, window.call_count)
        self.assertEqual({"output", "record"}, set(observe.call_args.kwargs["jobs_by_phase"]))
        dispatch.assert_not_called()

    def test_distinct_protected_record_dispatch_preserves_both_producers(self):
        signed_producer = {**self.producer, "commit": "e" * 40, "tree": "f" * 40,
                           "event": "workflow_dispatch", "runId": 88, "runAttempt": 1,
                           "pullRequest": None}
        result, seen, observed, window, dispatched = self.invoke(
            record_producer=signed_producer, record_workflow_sha="d" * 40,
            record_job_name="contract-phase10-record / contract-phase10-record",
        )
        self.assertEqual(self.producer, seen[0][3])
        self.assertEqual(signed_producer, seen[1][3])
        self.assertIn("-attestation-88-attempt-1", seen[1][2])
        self.assertEqual({"output"}, set(observed.call_args.kwargs["jobs_by_phase"]))
        dispatched.assert_called_once_with(signed_producer, workflow_sha="d" * 40,
                                            token="fixture-token")
        self.assertEqual(2, window.call_count)
        self.assertEqual(signed_producer, result["recordProducer"])
        transport = load_canonical_json_bytes((self.destination / "transport.json").read_bytes())
        self.assertEqual(self.producer, transport["producer"])
        self.assertEqual(signed_producer, transport["recordProducer"])

    def test_dispatch_rejects_unapproved_route_before_official_lookup(self):
        signed_producer = {**self.producer, "event": "workflow_dispatch", "runId": 88,
                           "runAttempt": 1, "pullRequest": None}
        with self.assertRaisesRegex(ValueError, "approved route"):
            self.invoke(record_producer=signed_producer, record_workflow_sha="d" * 40)
        self.assertFalse(self.destination.exists())

    def test_dispatch_observer_requires_exact_job_and_successful_run(self):
        signed_producer = {**self.producer, "commit": "e" * 40, "tree": "f" * 40,
                           "event": "workflow_dispatch", "runId": 88, "runAttempt": 1,
                           "pullRequest": None}
        run = {"id": 88, "run_attempt": 1, "path": ".github/workflows/ci.yml",
               "event": "workflow_dispatch", "status": "completed",
               "conclusion": "success", "head_sha": "e" * 40,
               "repository": {"full_name": signed_producer["repository"], "fork": False},
               "head_repository": {"full_name": signed_producer["repository"], "fork": False}}
        job = {"id": 93, "run_id": 88, "head_sha": "e" * 40,
               "name": "contract-phase10-record / contract-phase10-record",
               "status": "completed", "conclusion": "success"}
        with (patch.object(admission.products, "api_json", return_value=run),
              patch.object(admission.products, "_require_ci_workflow_reference") as route,
              patch.object(admission.products, "_observe_tested_commit", return_value={}) as commit,
              patch.object(admission.products, "paginated_items", return_value=[job])):
            observed = admission._observe_protected_record_dispatch(
                signed_producer, workflow_sha="d" * 40, token="fixture-token")
            self.assertEqual([job], observed["jobs"])
            self.assertIn(".github/workflows/contract-phase10-later-record.yml@" + "d" * 40,
                          route.call_args.args[1])
            self.assertTrue(commit.call_args.kwargs["allow_dispatch"])
        with (patch.object(admission.products, "api_json", return_value=run),
              patch.object(admission.products, "_require_ci_workflow_reference"),
              patch.object(admission.products, "_observe_tested_commit", return_value={}),
              patch.object(admission.products, "paginated_items", return_value=[
                  {**job, "name": "product-validation / contract-phase10-record"}])):
            with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
                admission._observe_protected_record_dispatch(
                    signed_producer, workflow_sha="d" * 40, token="fixture-token")

    def test_same_upload_id_cannot_satisfy_both_independent_inputs(self):
        with self.assertRaisesRegex(ValueError, "distinct official uploads"):
            self.invoke(record_id=17)

    def test_wrong_nested_record_job_fails_before_upload_download(self):
        with self.assertRaisesRegex(ValueError, "producer job is missing"):
            self.invoke(record_job_name="product-validation / contract-phase10-maven / sidecars")
        self.assertFalse(self.destination.exists())

    def test_mismatched_original_producer_fails_before_upload_lookup(self):
        changed = {**self.producer, "runAttempt": 3}
        with self.assertRaisesRegex(ValueError, "differs from the validated plan"):
            self.invoke(producer=changed)

    def test_signed_record_cannot_switch_the_original_producer(self):
        changed = {**self.producer, "runAttempt": 3}
        with self.assertRaisesRegex(ValueError, "differs from caller-pinned"):
            self.invoke(recorded_producer=changed)
        self.assertFalse(self.destination.exists())

    def test_post_verification_snapshot_mutation_cannot_be_published(self):
        with self.assertRaisesRegex(ValueError, "inputs changed before reuse capture"):
            self.invoke(mutate_snapshot=True)
        self.assertFalse(self.destination.exists())

    def test_cli_requires_independently_pinned_canonical_original_producer(self):
        producer_file = self.root / "producer.json"
        producer_file.write_bytes(canonical_json_bytes(self.producer))
        arguments = ["--plan", str(self.plan),
                     "--validation-repository", str(self.validation),
                     "--trusted-repository", str(self.trusted),
                     "--destination", str(self.destination),
                     "--original-producer", str(producer_file),
                     "--expected-original-producer-sha256", sha256_bytes(b"wrong"),
                     "--trusted-source-commit", "c" * 40,
                     "--trusted-workflow-sha", "c" * 40,
                     "--trusted-workflow-path", ".github/workflows/contract-phase10-output-record.yml",
                     "--output-job-name", "product-validation / contract-phase10-output-record / contract-phase10-output",
                     "--record-job-name", "product-validation / contract-phase10-output-record / contract-phase10-record",
                     "--expected-pgp-key-sha256", "sha256:" + "d" * 64,
                     "--output-artifact-id", "17",
                     "--output-artifact-sha256", sha256_file(self.archives["output"]),
                     "--record-artifact-id", "18",
                     "--record-artifact-sha256", sha256_file(self.archives["record"])]
        with (patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-token"}),
              patch.object(admission, "capture_reusable_contract_phase10_output") as capture,
              self.assertRaisesRegex(ValueError, "independent digest")):
            admission.main(arguments)
        capture.assert_not_called()
        arguments[arguments.index("--expected-original-producer-sha256") + 1] = sha256_bytes(
            producer_file.read_bytes())
        with (patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-token"}),
              patch.object(admission, "capture_reusable_contract_phase10_output",
                           return_value={"files": []}) as capture,
              redirect_stdout(StringIO()) as printed):
            self.assertEqual(0, admission.main(arguments))
        self.assertEqual(self.producer, capture.call_args.kwargs["original_producer"])
        self.assertEqual(17, capture.call_args.kwargs["output_artifact_id"])
        self.assertEqual(18, capture.call_args.kwargs["record_artifact_id"])
        self.assertEqual({"destination": str(self.destination), "files": []},
                         json.loads(printed.getvalue()))

    def test_cli_requires_independent_record_dispatch_producer_digest(self):
        original = self.root / "producer.json"
        original.write_bytes(canonical_json_bytes(self.producer))
        signed_producer = {**self.producer, "event": "workflow_dispatch", "runId": 88,
                           "runAttempt": 1, "pullRequest": None}
        dispatch = self.root / "record-producer.json"
        dispatch.write_bytes(canonical_json_bytes(signed_producer))
        args = ["--plan", str(self.plan), "--validation-repository", str(self.validation),
                "--trusted-repository", str(self.trusted), "--destination", str(self.destination),
                "--original-producer", str(original),
                "--expected-original-producer-sha256", sha256_bytes(original.read_bytes()),
                "--record-producer", str(dispatch),
                "--expected-record-producer-sha256", sha256_bytes(b"wrong"),
                "--trusted-source-commit", "c" * 40, "--trusted-workflow-sha", "c" * 40,
                "--trusted-workflow-path", ".github/workflows/contract-phase10-output-record.yml",
                "--trusted-record-workflow-sha", "d" * 40,
                "--output-job-name", "product-validation / contract-phase10-output-record / contract-phase10-output",
                "--record-job-name", "contract-phase10-record / contract-phase10-record",
                "--expected-pgp-key-sha256", "sha256:" + "d" * 64,
                "--output-artifact-id", "17",
                "--output-artifact-sha256", sha256_file(self.archives["output"]),
                "--record-artifact-id", "18",
                "--record-artifact-sha256", sha256_file(self.archives["record"])]
        with (patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-token"}),
              patch.object(admission, "capture_reusable_contract_phase10_output") as capture,
              self.assertRaisesRegex(ValueError, "independent digest")):
            admission.main(args)
        capture.assert_not_called()
        args[args.index("--expected-record-producer-sha256") + 1] = sha256_bytes(
            dispatch.read_bytes())
        with (patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-token"}),
              patch.object(admission, "capture_reusable_contract_phase10_output",
                           return_value={"files": []}) as capture,
              redirect_stdout(StringIO())):
            self.assertEqual(0, admission.main(args))
        self.assertEqual(signed_producer, capture.call_args.kwargs["record_producer"])


if __name__ == "__main__":
    unittest.main()
