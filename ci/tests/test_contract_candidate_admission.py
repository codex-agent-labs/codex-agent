"""Candidate admission joins independently pinned Contract originals, never signs."""

from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from ci import contract_candidate_admission as candidate
from ci import impact
from ci.contract_catalog_promotion import stage_promoted_contract_catalog
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes,
)
from ci.products.restore import verify_phase_shard
from ci.products.registry import PhaseInstanceId
from ci.products.signatures import sign_manifest
from ci.tests import test_contract_phase10_maven_caller as phase10_fixture
from ci.tests.test_contract_ci_originals import archive_tree
from ci.tests.test_product_reuse_adapter import impact_plan


_A = "a" * 40
_B = "b" * 40
_C = "c" * 40
_D = "d" * 40
_DIGEST = "sha256:" + "1" * 64
_VERSION = "0.8.0"


def _producer(event: str, run: int, *, commit: str = _A) -> dict:
    return {"repository": candidate._REPOSITORY,
            "workflowPath": ".github/workflows/promote.yml" if event == "push"
                            else ".github/workflows/ci.yml",
            "event": event, "commit": commit, "tree": _B,
            "pullRequest": 31 if event == "pull_request" else None,
            "runId": run, "runAttempt": 1}


def _pins() -> dict:
    return {"expected_inventory_sha256": _DIGEST,
            "expected_contract_version": _VERSION,
            "expected_payload_sha256": _DIGEST,
            "expected_metadata_build_key": _DIGEST,
            "expected_source_commit": _C,
            "expected_source_tree": _D,
            "expected_validation_tree": _B,
            "expected_workflow_sha": _C,
            "expected_caller_sha256": _DIGEST,
            "expected_keyring_sha256": _DIGEST,
            "expected_keys_inventory_sha256": _DIGEST,
            "expected_pgp_key_sha256": _DIGEST}


def _selection() -> dict:
    return {"schemaVersion": 1,
            "catalog": {"producer": _producer("push", 10),
                        "trustedWorkflowSha": _C,
                        "jobName": "Promote / contract-promoted-catalog / contract-promoted-catalog",
                        "artifactId": 20, "artifactSha256": _DIGEST,
                        "indexSha256": _DIGEST, "inventorySha256": _DIGEST},
            "phase10": {"originalProducer": _producer("pull_request", 11),
                        "recordProducer": _producer("workflow_dispatch", 12),
                        "trustedSourceCommit": _C, "trustedWorkflowSha": _C,
                        "trustedRecordWorkflowSha": _C,
                        "expectedPgpKeySha256": _DIGEST,
                        "outputArtifactId": 21, "outputArtifactSha256": _DIGEST,
                        "recordArtifactId": 22, "recordArtifactSha256": _DIGEST,
                        "recordSha256": _DIGEST, "signatureSha256": _DIGEST,
                        "phase11Pins": _pins()}}


class ContractCandidateAdmissionTest(unittest.TestCase):
    def test_cli_rejects_selection_without_independent_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            selected = root / "selection.json"
            selected.write_bytes(canonical_json_bytes(_selection()))
            arguments = ["--selection", str(selected), "--expected-selection-sha256", _DIGEST,
                         "--plan", str(selected), "--trusted-repository", str(root),
                         "--validation-repository", str(root), "--landed-repository", str(root),
                         "--destination", str(root / "candidate")]
            with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}), \
                 patch.object(candidate, "admit_contract_candidate") as admitted, \
                 self.assertRaisesRegex(ValueError, "protected S1048 digest"):
                candidate.main(arguments)
            admitted.assert_not_called()

    def test_selection_rejects_cross_tree_before_network(self):
        selected = _selection()
        selected["catalog"]["producer"]["tree"] = _D
        with self.assertRaisesRegex(ValueError, "inconsistent source or tree"):
            candidate._selection(selected)

    def test_promoted_observation_requires_successful_main_and_exact_child(self):
        producer = _producer("push", 10)
        job = {"id": 40, "run_id": 10, "head_sha": _A, "name": "promoted-catalog",
               "status": "completed", "conclusion": "success"}
        run = {"id": 10, "run_attempt": 1, "path": producer["workflowPath"],
               "event": "push", "head_branch": "main", "head_sha": _A,
               "status": "completed", "conclusion": "success",
               "repository": {"full_name": candidate._REPOSITORY, "fork": False},
               "head_repository": {"full_name": candidate._REPOSITORY, "fork": False}}
        commit = {"sha": _A, "tree": {"sha": _B}}
        def api(url, _token):
            return commit if "/git/commits/" in url else run
        with patch.object(candidate.transport, "api_json", side_effect=api), \
             patch.object(candidate.transport, "paginated_items", return_value=[job]), \
             patch.object(candidate.transport, "_require_ci_workflow_reference") as workflow:
            self.assertEqual(candidate._observe_catalog(producer, _C, "promoted-catalog", "token")["run"], run)
            workflow.assert_called_once_with(run,
                f"{candidate._REPOSITORY}/{candidate._CATALOG_WORKFLOW}@{_C}", _C)
            run["head_branch"] = "feature"
            with self.assertRaisesRegex(ValueError, "official main run"):
                candidate._observe_catalog(producer, _C, "promoted-catalog", "token")

    def test_join_forwards_only_when_catalog_record_and_official_bytes_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("trusted", "validation", "landed"):
                (root / name).mkdir()
            (root / "plan.json").write_text("{}\n")
            catalog_directory = root / "source-catalog"
            catalog_directory.mkdir()
            (catalog_directory / "product-index.json").write_bytes(b"index\n")
            (catalog_directory / "product-index.sig").write_bytes(b"signature\n")
            closure = catalog_directory / "execution-closure/receipts"
            closure.mkdir(parents=True)
            (closure / "metadata.json").write_bytes(b"original-metadata\n")
            for suffix in ("json", "sig"):
                (catalog_directory / f"codex-agent-contract-{_VERSION}.attestation.{suffix}").write_bytes(
                    f"attestation-{suffix}\n".encode())
            archive = root / "catalog.zip"
            with ZipFile(archive, "w") as output:
                for file in catalog_directory.rglob("*"):
                    if file.is_file():
                        output.write(file, file.relative_to(catalog_directory).as_posix())
            selected = _selection()
            selected["catalog"]["artifactSha256"] = candidate.sha256_file(archive)
            selected["catalog"]["indexSha256"] = candidate.sha256_file(
                catalog_directory / "product-index.json")
            selected["catalog"]["inventorySha256"] = sha256_bytes(
                canonical_json_bytes(regular_file_inventory(catalog_directory)))
            receipt = b"signed-record\n"
            signature = b"signed-signature\n"
            selected["phase10"]["recordSha256"] = sha256_bytes(receipt)
            selected["phase10"]["signatureSha256"] = sha256_bytes(signature)
            entries = [{"product": "contract", "component": "contract", "phase": phase,
                        "target": "common", "productVersion": _VERSION,
                        "buildKey": _DIGEST, "artifactSha256": _DIGEST,
                        "receiptSha256": candidate.sha256_file(closure / "metadata.json")}
                       for phase in candidate._PHASES]
            index = {"producer": selected["catalog"]["producer"],
                     "context": {"kind": "promoted-main", "tree": _B},
                     "trustDomain": "release", "entries": entries}
            def download(_id, _sha, _name, _producer, _run, _token, *, destination):
                destination.write_bytes(archive.read_bytes())
                return {"id": 20}, destination
            tamper = {"closure": False}
            def capture(_plan, _validation, _trusted, destination, **_kwargs):
                (destination / "signed-record").mkdir(parents=True)
                (destination / "signed-record/record.json").write_bytes(receipt)
                (destination / "signed-record/record.sig").write_bytes(signature)
                (destination / "output").mkdir()
                handoff = destination / "output/contract-release-evidence/contract-input"
                (handoff / "execution-closure/receipts").mkdir(parents=True)
                (handoff / "execution-closure/receipts/metadata.json").write_bytes(
                    b"switched-metadata\n" if tamper["closure"] else
                    (closure / "metadata.json").read_bytes())
                for suffix in ("json", "sig"):
                    name = f"codex-agent-contract-{_VERSION}.attestation.{suffix}"
                    (handoff / name).write_bytes((catalog_directory / name).read_bytes())
                return {"record": {"phase11Pins": selected["phase10"]["phase11Pins"],
                                   "officialUpload": {"producer": selected["phase10"]["originalProducer"]}}}
            def forward(_source, destination, **_kwargs):
                destination.mkdir()
                return {"product": "contract"}
            fake_trust = type("Trust", (), {"keyring": root / "keyring", "keys": root / "keys"})()
            with patch.object(candidate, "_observe_catalog", return_value={"run": {}}), \
                 patch.object(candidate.transport, "_download_contract_ci_upload", side_effect=download), \
                 patch.object(candidate.transport, "_require_artifact_job_window"), \
                 patch.object(candidate.transport, "_release_trust", return_value=fake_trust), \
                 patch.object(candidate, "verify_release_product_index", return_value=(index, b"index\n")), \
                 patch.object(candidate.transport, "stage_release_catalog"), \
                 patch.object(candidate, "capture_reusable_contract_phase10_output", side_effect=capture), \
                 patch.object(candidate, "forward_verified_contract_phase10_bytes", side_effect=forward) as forwarded:
                result = candidate.admit_contract_candidate(
                    selected, root / "plan.json", root / "trusted", root / "validation",
                    root / "landed", root / "candidate", token="token", environ={})
                self.assertEqual(result["candidate"]["product"], "contract")
                forwarded.assert_called_once()
                mismatched = copy.deepcopy(selected)
                mismatched["phase10"]["phase11Pins"]["expected_payload_sha256"] = "sha256:" + "2" * 64
                with self.assertRaisesRegex(ValueError, "disagree"):
                    candidate.admit_contract_candidate(
                        mismatched, root / "plan.json", root / "trusted", root / "validation",
                        root / "landed", root / "rejected", token="token", environ={})
                self.assertFalse((root / "rejected").exists())
                tamper["closure"] = True
                with self.assertRaisesRegex(ValueError, "different original closure"):
                    candidate.admit_contract_candidate(
                        selected, root / "plan.json", root / "trusted", root / "validation",
                        root / "landed", root / "switched", token="token", environ={})
                self.assertFalse((root / "switched").exists())


@unittest.skipUnless(shutil.which("gpg") and shutil.which("ssh-keygen"),
                     "GnuPG and OpenSSH are required")
class ContractCandidateSignedChainTest(unittest.TestCase):
    def test_real_signed_catalog_record_and_forwarder_join_exact_bytes(self):
        # Only official HTTP/Git observations are synthetic; catalog, signed
        # record, original-object and Phase-11 byte verifiers execute for real.
        phase10 = phase10_fixture.ContractPhase10MavenCallerTest(
            "test_exact_original_payload_and_external_phase10_maven_sidecars")
        self.addCleanup(phase10.doClassCleanups)
        phase10.setUpClass()
        self.addCleanup(phase10.doCleanups)
        phase10.setUp()
        with patch("reuse.api_request", side_effect=phase10.fixture.api()):
            control = phase10.invoke()
        fixture = phase10.fixture
        root = fixture.root
        handoff = phase10.destination / "contract-release-evidence/contract-input"
        source_tree = subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=fixture.repository_root,
            text=True).strip()
        promoted_producer = {"repository": candidate._REPOSITORY,
                             "workflowPath": ".github/workflows/promote.yml",
                             "event": "push", "commit": fixture.source_sha,
                             "tree": fixture.producer["tree"], "pullRequest": None,
                             "runId": 300, "runAttempt": 1}
        phase_objects = {}
        phase_pins = {}
        for phase in candidate._PHASES:
            receipt_bytes = fixture.receipts[phase].read_bytes()
            receipt = load_canonical_json_bytes(receipt_bytes)
            verified = verify_phase_shard(
                fixture.shards[phase], PhaseInstanceId("contract", "contract", phase, "common"))
            phase_objects[phase] = fixture.shards[phase] / verified["objectPath"]
            phase_pins[phase] = {
                "buildKey": receipt["buildKey"],
                "receiptSha256": sha256_bytes(receipt_bytes),
                "objectSha256": verified["objectSha256"],
                "artifactPath": receipt["outputs"][0]["relativePath"],
                "producer": receipt["producer"],
            }
        catalog = root / "promoted-catalog"
        stage_promoted_contract_catalog(
            handoff, phase_objects, phase_pins, catalog,
            repository=candidate._REPOSITORY,
            context={"kind": "promoted-main", "commit": promoted_producer["commit"],
                     "tree": promoted_producer["tree"], "promotionRunId": 300,
                     "promotionRunAttempt": 1},
            producer=promoted_producer, keyring=fixture.keyring,
            keys_directory=fixture.keys, private_key=fixture.private_key,
        )
        release = phase10.destination / "contract-release-evidence"
        pins = {
            "expected_inventory_sha256": sha256_bytes(canonical_json_bytes(
                regular_file_inventory(phase10.destination))),
            "expected_contract_version": control["contractInventory"]["contractVersion"],
            "expected_payload_sha256": control["mavenSidecars"]["payloadSha256"],
            "expected_metadata_build_key": control["contractInventory"]["metadataBuildKey"],
            "expected_source_commit": fixture.source_sha,
            "expected_source_tree": source_tree,
            "expected_validation_tree": fixture.producer["tree"],
            "expected_workflow_sha": fixture.pin,
            "expected_caller_sha256": sha256_bytes((release / "caller.json").read_bytes()),
            "expected_keyring_sha256": sha256_bytes(fixture.keyring.read_bytes()),
            "expected_keys_inventory_sha256": sha256_bytes(canonical_json_bytes(
                regular_file_inventory(fixture.keys))),
            "expected_pgp_key_sha256": sha256_bytes(phase10.key.read_bytes()),
        }
        archives = {30: archive_tree(catalog), 31: archive_tree(phase10.destination)}
        observation = {"artifactId": 31, "artifactSha256": sha256_bytes(archives[31]),
                       "artifactName": ("codex-agent-contract-phase10-maven-"
                                        f"{fixture.producer['tree']}-attempt-2"),
                       "inventorySha256": pins["expected_inventory_sha256"],
                       "producer": fixture.producer,
                       "trustedWorkflowPath": candidate._OUTPUT_WORKFLOW,
                       "trustedWorkflowSha": fixture.pin,
                       "trustedJobName": candidate._OUTPUT_JOB}
        record = {"schemaVersion": 1, "product": "contract", "signing": fixture.signing,
                  "trustedSourceCommit": fixture.source_sha,
                  "officialUpload": observation, "phase11Pins": pins,
                  "outputFiles": regular_file_inventory(phase10.destination)}
        signed_record = root / "signed-record"
        signed_record.mkdir()
        record_path = signed_record / "record.json"
        record_path.write_bytes(canonical_json_bytes(record))
        signature_path = sign_manifest(record_path, fixture.private_key, fixture.signing)
        self.assertEqual(signed_record / "record.sig", signature_path)
        archives[32] = archive_tree(signed_record)
        record_producer = {**fixture.producer, "event": "workflow_dispatch",
                           "commit": fixture.source_sha, "tree": source_tree,
                           "runId": 301, "runAttempt": 1, "pullRequest": None}
        selected = {"schemaVersion": 1, "catalog": {
            "producer": promoted_producer, "trustedWorkflowSha": fixture.pin,
            "jobName": "Promote / contract-promoted-catalog / contract-promoted-catalog",
            "artifactId": 30, "artifactSha256": sha256_bytes(archives[30]),
            "indexSha256": candidate.sha256_file(catalog / "product-index.json"),
            "inventorySha256": sha256_bytes(canonical_json_bytes(
                regular_file_inventory(catalog))),
        }, "phase10": {
            "originalProducer": fixture.producer, "recordProducer": record_producer,
            "trustedSourceCommit": fixture.source_sha,
            "trustedWorkflowSha": fixture.pin,
            "trustedRecordWorkflowSha": fixture.pin,
            "expectedPgpKeySha256": pins["expected_pgp_key_sha256"],
            "outputArtifactId": 31, "outputArtifactSha256": sha256_bytes(archives[31]),
            "recordArtifactId": 32, "recordArtifactSha256": sha256_bytes(archives[32]),
            "recordSha256": candidate.sha256_file(record_path),
            "signatureSha256": candidate.sha256_file(signature_path),
            "phase11Pins": pins,
        }}
        plan = impact_plan(changed=[])
        plan["validationCommit"] = fixture.producer["commit"]
        plan["validationTree"] = fixture.producer["tree"]
        plan["headCommit"] = fixture.producer["commit"]
        validation_checkout = Path(__file__).resolve().parents[2]
        lanes, full, unknown = impact._legacy_lane_states(
            validation_checkout, plan["changedPaths"], force_full=plan["fullRequested"],
            remote_authorized=True,
            remote_reason=plan["remoteBuildAuthorizationReason"],
        )
        plan.update(lanes=lanes, full=full, unknownPaths=unknown)
        plan_path = root / "impact-plan.json"
        plan_path.write_bytes(canonical_json_bytes(plan))
        job = lambda name, run, head: {"id": run + 1000, "run_id": run,
            "head_sha": head, "name": name, "status": "completed",
            "conclusion": "success", "started_at": "2026-09-06T10:00:00Z",
            "completed_at": "2026-09-06T10:30:00Z"}
        original_observation = {"run": {"head_sha": fixture.run["head_sha"]},
                                "jobs": [job(candidate._OUTPUT_JOB, 71, fixture.run["head_sha"])]}
        record_observation = {"run": {"head_sha": fixture.source_sha},
                              "jobs": [job(candidate._RECORD_JOB, 301, fixture.source_sha)]}
        catalog_observation = {"run": {"head_sha": fixture.source_sha},
                               "jobs": [job(selected["catalog"]["jobName"], 300, fixture.source_sha)]}
        artifacts = {artifact_id: {"id": artifact_id, "digest": sha256_bytes(raw),
            "created_at": "2026-09-06T10:15:00Z"}
            for artifact_id, raw in archives.items()}
        def download(artifact_id, digest, _name, _producer, _run, _token, *, destination):
            self.assertEqual(digest, artifacts[artifact_id]["digest"])
            destination.write_bytes(archives[artifact_id])
            return artifacts[artifact_id], destination
        def git_value(_root, _command, revision):
            if revision == "HEAD^{commit}":
                return fixture.producer["commit"]
            if revision == "HEAD^{tree}":
                return fixture.producer["tree"]
            if revision == f"{fixture.source_sha}^{{tree}}":
                return source_tree
            raise AssertionError(f"unexpected Git observation: {revision}")
        destination = root / "candidate-exact"
        with patch.object(candidate, "_observe_catalog", return_value=catalog_observation), \
             patch.object(candidate.transport, "_download_contract_ci_upload", side_effect=download), \
             patch.object(candidate.transport, "_observe_ci_producer_jobs",
                          return_value=[original_observation]), \
             patch("ci.contract_phase10_reuse_admission._observe_protected_record_dispatch",
                   return_value=record_observation), \
             patch("ci.contract_phase10_output_record.observe_contract_phase10_upload",
                   return_value=observation), \
             patch.object(candidate.transport, "_git_value", side_effect=git_value), \
             patch("ci.contract_phase11_bytes._landed_tree",
                   return_value=fixture.producer["tree"]):
            accepted = candidate.admit_contract_candidate(
                selected, plan_path, fixture.repository_root, validation_checkout,
                validation_checkout, destination, token="fixture-token", environ={})
            self.assertEqual(pins["expected_payload_sha256"], accepted["candidate"]["payloadSha256"])
            self.assertEqual(regular_file_inventory(phase10.destination),
                             regular_file_inventory(destination))
            self.assertEqual((phase10.destination / "sidecar-selection.json").read_bytes(),
                             (destination / "sidecar-selection.json").read_bytes())
            altered = copy.deepcopy(selected)
            altered["catalog"]["indexSha256"] = "sha256:" + "0" * 64
            with self.assertRaisesRegex(ValueError, "independent S1048 pins"):
                candidate.admit_contract_candidate(
                    altered, plan_path, fixture.repository_root, validation_checkout,
                    validation_checkout, root / "tampered-index", token="fixture-token", environ={})
            self.assertFalse((root / "tampered-index").exists())
            tampered_catalog = root / "tampered-catalog"
            shutil.copytree(catalog, tampered_catalog)
            (tampered_catalog / "product-index.json").write_bytes(
                (catalog / "product-index.json").read_bytes() + b"changed\n")
            archives[30] = archive_tree(tampered_catalog)
            with self.assertRaisesRegex(ValueError, "independent S1048 pins"):
                candidate.admit_contract_candidate(
                    selected, plan_path, fixture.repository_root, validation_checkout,
                    validation_checkout, root / "tampered-upload", token="fixture-token", environ={})
            self.assertFalse((root / "tampered-upload").exists())


if __name__ == "__main__":
    unittest.main()
