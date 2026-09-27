"""A signed Runtime record cannot replace source, upload or deep-product proof."""

from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from ci import runtime_phase10_output_record as gate
from ci import runtime_phase10_record_signer as signer
from ci.products.inventory import (
    canonical_json_bytes, public_key_fingerprint, regular_file_inventory,
    sha256_bytes, write_canonical_json,
)
from ci.products.signatures import generate_development_key, sign_manifest


@unittest.skipUnless(shutil.which("git") and shutil.which("ssh-keygen"),
                     "Git and OpenSSH are required")
class RuntimePhase10OutputRecordTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="rt-phase10-record-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.private, public, development = generate_development_key(self.root / "key")
        self.signing = {**development, "trustDomain": "release", "keyId": "test-release"}
        keyring = self.repository / "gradle/release/product-signing-keys.json"
        keyring.parent.mkdir(parents=True)
        keys = self.repository / "gradle/release/keys"
        keys.mkdir()
        (keys / "test-release.pub").write_bytes(public.read_bytes())
        write_canonical_json(keyring, {
            "schemaVersion": 1, "namespace": self.signing["namespace"],
            "algorithm": self.signing["algorithm"], "trustDomain": "release",
            "activeKey": {"keyId": "test-release",
                          "fingerprint": public_key_fingerprint(public.read_bytes())},
            "retiredKeys": [],
        })
        subprocess.run(["git", "init", "-q"], cwd=self.repository, check=True)
        subprocess.run(["git", "add", "."], cwd=self.repository, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "-qm", "trust"],
                       cwd=self.repository, check=True)
        self.commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.repository, text=True,
        ).strip()
        self.tree = subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=self.repository, text=True,
        ).strip()
        # The signer source and landed validation checkout are independent.
        self.validation = self.root / "validation"
        self.validation.mkdir()
        (self.validation / "candidate.txt").write_text("candidate\n")
        subprocess.run(["git", "init", "-q"], cwd=self.validation, check=True)
        subprocess.run(["git", "add", "."], cwd=self.validation, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "-qm", "candidate"],
                       cwd=self.validation, check=True)
        self.candidate_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.validation, text=True,
        ).strip()
        self.candidate_tree = subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=self.validation, text=True,
        ).strip()
        self.output = self.root / "phase10-runtime"
        self.output.mkdir()
        (self.output / "caller.json").write_bytes(b"selected\n")
        self.sidecars = self.root / "phase10-maven"
        self.sidecars.mkdir()
        (self.sidecars / "signature.asc").write_bytes(b"signature\n")
        self.pgp = self.root / "pgp-public-key.asc"
        self.pgp.write_bytes(b"original PGP public key\n")
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"plan\n")
        self.record_path = self.root / "record.json"
        self.upload = {
            "artifact": {"id": 27, "digest": "sha256:" + "a" * 64},
            "captureProducer": {"commit": self.candidate_commit, "tree": self.candidate_tree},
            "observed": [],
            "aggregateBuildKey": "sha256:" + "b" * 64,
            "aggregateReceiptSha256": "sha256:" + "c" * 64,
        }
        self.pins = {
            "expected_protected_inventory_sha256": sha256_bytes(
                canonical_json_bytes(regular_file_inventory(self.output, allow_empty=True))),
            "expected_sidecar_inventory_sha256": sha256_bytes(
                canonical_json_bytes(regular_file_inventory(self.sidecars))),
            "expected_metadata_receipt_sha256": self.upload["aggregateReceiptSha256"],
            "expected_build_key": self.upload["aggregateBuildKey"],
            "expected_runtime_version": "0.8.0",
            "expected_manifest_sha256": "sha256:" + "d" * 64,
            "expected_source_commit": self.commit,
            "expected_source_tree": self.tree,
            "expected_validation_tree": self.candidate_tree,
            "expected_workflow_sha": "e" * 40,
            "expected_keyring_sha256": sha256_bytes(keyring.read_bytes()),
            "expected_keys_inventory_sha256": sha256_bytes(
                canonical_json_bytes(regular_file_inventory(keys))),
            "expected_pgp_key_sha256": sha256_bytes(self.pgp.read_bytes()),
        }
        self.record = {
            "schemaVersion": 1, "product": "runtime", "signing": self.signing,
            "trustedSourceCommit": self.commit, "officialUpload": deepcopy(self.upload),
            "phase11Pins": self.pins,
            "protectedFiles": regular_file_inventory(self.output, allow_empty=True),
            "sidecarFiles": regular_file_inventory(self.sidecars),
        }
        self.sign()

    def sign(self):
        if self.record_path.exists():
            self.record_path.unlink()
        signature = self.record_path.with_suffix(".sig")
        if signature.exists():
            signature.unlink()
        write_canonical_json(self.record_path, self.record)
        self.signature = sign_manifest(self.record_path, self.private, self.signing)

    def verify(self, *, deep=True, **overrides):
        args = dict(
            validation_repository=self.validation,
            trusted_source_commit=self.commit, trusted_workflow_sha="e" * 40,
            expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
            token="local-test-token", environ={},
        )
        args.update(overrides)

        def captured(_, __, destination, **kwargs):
            self.assertEqual(self.validation, Path(__))
            self.assertEqual(self.pins["expected_build_key"], kwargs["expected_build_key"])
            (destination / "original").mkdir(parents=True)
            shutil.copy2(self.output / "caller.json", destination / "original/caller.json")
            return deepcopy(self.upload)

        with patch.object(gate, "capture_observed_runtime_phase10_upload",
                          side_effect=captured) as official:
            if deep:
                with patch.object(gate, "forward_verified_runtime_phase10_bytes") as verifier:
                    result = gate.verify_signed_runtime_phase10_output_record(
                        self.record_path, self.signature, self.repository, self.output,
                        self.sidecars, self.pgp, self.plan, **args,
                    )
                    verifier.assert_called_once()
                    self.assertEqual(self.pins, {key: value for key, value in
                                      verifier.call_args.kwargs.items() if key.startswith("expected_")})
            else:
                result = gate.verify_signed_runtime_phase10_output_record(
                    self.record_path, self.signature, self.repository, self.output,
                    self.sidecars, self.pgp, self.plan, **args,
                )
            official.assert_called_once()
            return result

    def test_signed_record_binds_official_capture_and_exact_bytes(self):
        self.assertNotEqual(self.commit, self.candidate_commit)
        self.assertEqual(self.record, self.verify())
        (self.sidecars / "signature.asc").write_bytes(b"tampered\n")
        with self.assertRaisesRegex(ValueError, "sidecars"):
            self.verify()

    def admit_original(self, *, overrides=None, archive_files=None, plan=None):
        producer = {
            "repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml",
            "commit": self.candidate_commit, "tree": self.candidate_tree,
            "event": "pull_request", "runId": 77, "runAttempt": 2,
            "pullRequest": 31,
        }
        selected = {
            "repository": producer["repository"], "validationCommit": producer["commit"],
            "validationTree": producer["tree"], "event": producer["event"],
            "pullRequest": producer["pullRequest"], "remoteBuildAuthorized": True,
        }
        if plan is not None:
            selected.update(plan)
        files = archive_files or {"record.json": self.record_path.read_bytes(),
                                  "record.sig": self.signature.read_bytes()}
        archive = self.root / "original-record.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zipped:
            for name, raw in sorted(files.items()):
                zipped.writestr(name, raw)
        artifact_sha = sha256_bytes(archive.read_bytes())
        inputs = dict(expected_producer=producer,
            trusted_record_workflow_path=".github/workflows/runtime-phase10-output-record.yml",
            trusted_record_workflow_sha="f" * 40,
            trusted_record_job_name="product-validation / runtime-phase10-output-record",
            record_artifact_name="runtime-record-original-77-2",
            record_artifact_id=27, record_artifact_sha256=artifact_sha,
            expected_record_sha256=sha256_bytes(self.record_path.read_bytes()),
            expected_signature_sha256=sha256_bytes(self.signature.read_bytes()),
            trusted_source_commit=self.commit,
            trusted_aggregate_workflow_sha="e" * 40,
            expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
            token="local-test-token", environ={"GITHUB_RUN_ID": "999"})
        inputs.update(overrides or {})

        def official(_, __, destination, **kwargs):
            self.assertEqual("77", kwargs["environ"]["GITHUB_RUN_ID"])
            self.assertEqual("2", kwargs["environ"]["GITHUB_RUN_ATTEMPT"])
            (destination / "original").mkdir(parents=True)
            shutil.copy2(self.output / "caller.json", destination / "original/caller.json")
            return deepcopy(self.upload)

        def download(artifact_id, digest, name, pinned_producer, run, token, *, destination):
            self.assertEqual(27, artifact_id)
            self.assertEqual(artifact_sha, digest)
            self.assertEqual(inputs["record_artifact_name"], name)
            self.assertEqual(producer, pinned_producer)
            shutil.copy2(archive, destination)
            return {"id": 27, "digest": artifact_sha}, destination

        with patch.object(gate.product_reuse, "_validate_plan", return_value=selected), \
             patch.object(gate.product_reuse, "_observe_ci_producer_jobs",
                          return_value=[{"run": {"head_sha": self.candidate_commit}, "jobs": []}]), \
             patch.object(gate.product_reuse, "_download_contract_ci_upload",
                          side_effect=download) as fetched, \
             patch.object(gate.product_reuse, "_require_artifact_job_window") as window, \
             patch.object(gate, "capture_observed_runtime_phase10_upload", side_effect=official), \
             patch.object(gate, "forward_verified_runtime_phase10_bytes") as deep:
            result = gate.admit_original_runtime_phase10_output_record(
                self.plan, self.validation, self.repository, self.output,
                self.sidecars, self.pgp, self.root / "admitted-record", **inputs)
        return result, fetched, window, deep

    def test_later_run_admits_only_official_pinned_signed_original(self):
        result, fetched, window, deep = self.admit_original()
        self.assertEqual(self.record, result["record"])
        self.assertEqual(27, result["officialRecordUpload"]["artifact"]["id"])
        self.assertEqual(self.record_path.read_bytes(), result["recordPath"].read_bytes())
        self.assertEqual(self.signature.read_bytes(), result["signaturePath"].read_bytes())
        self.assertEqual(result["retainedFiles"], regular_file_inventory(self.root / "admitted-record"))
        self.assertEqual(result["recordSha256"], sha256_bytes(result["recordPath"].read_bytes()))
        self.assertEqual(result["signatureSha256"], sha256_bytes(result["signaturePath"].read_bytes()))
        fetched.assert_called_once()
        window.assert_called_once()
        deep.assert_called_once()

    def test_later_run_rejects_signed_pair_changed_after_deep_verification(self):
        original = gate.verify_signed_runtime_phase10_output_record

        def mutate_after_verify(record_path, *args, **kwargs):
            verified = original(record_path, *args, **kwargs)
            record_path.write_bytes(b"changed after verification\n")
            return verified

        with patch.object(gate, "verify_signed_runtime_phase10_output_record",
                          side_effect=mutate_after_verify), \
             self.assertRaisesRegex(ValueError, "changed during admission"):
            self.admit_original()
        self.assertFalse((self.root / "admitted-record").exists())

    def test_later_run_rejects_wrong_producer_before_record_download(self):
        with self.assertRaisesRegex(ValueError, "producer differs"):
            self.admit_original(plan={"validationTree": "0" * 40})

    def test_later_run_rejects_record_or_signature_not_independently_pinned(self):
        for field in ("expected_record_sha256", "expected_signature_sha256"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "independent pins"):
                self.admit_original(overrides={field: "sha256:" + "0" * 64})

    def test_later_run_rejects_extra_official_record_member(self):
        with self.assertRaisesRegex(ValueError, "unexpected files"):
            self.admit_original(archive_files={
                "record.json": self.record_path.read_bytes(),
                "record.sig": self.signature.read_bytes(), "extra.txt": b"not allowed",
            })

    def test_original_admission_cli_requires_independently_pinned_producer(self):
        producer = {
            "repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml",
            "commit": self.candidate_commit, "tree": self.candidate_tree,
            "event": "pull_request", "runId": 77, "runAttempt": 2,
            "pullRequest": 31,
        }
        producer_path = self.root / "original-producer.json"
        producer_path.write_bytes(canonical_json_bytes(producer))
        args = ["admit-original", "--plan", str(self.plan),
                "--validation-repository", str(self.validation),
                "--repository-root", str(self.repository),
                "--protected-output", str(self.output),
                "--maven-sidecars", str(self.sidecars),
                "--pgp-public-key", str(self.pgp),
                "--destination", str(self.root / "admitted-record"),
                "--original-producer", str(producer_path),
                "--expected-original-producer-sha256", "sha256:" + "0" * 64,
                "--trusted-record-workflow-path", ".github/workflows/runtime-phase10-output-record.yml",
                "--trusted-record-workflow-sha", "f" * 40,
                "--trusted-record-job-name", "product-validation / runtime-phase10-output-record",
                "--record-artifact-name", "runtime-record-original-77-2",
                "--record-artifact-id", "27",
                "--record-artifact-sha256", "sha256:" + "a" * 64,
                "--expected-record-sha256", sha256_bytes(self.record_path.read_bytes()),
                "--expected-signature-sha256", sha256_bytes(self.signature.read_bytes()),
                "--trusted-source-commit", self.commit,
                "--trusted-aggregate-workflow-sha", "e" * 40,
                "--expected-pgp-key-sha256", self.pins["expected_pgp_key_sha256"]]
        with patch.dict(os.environ, {"GITHUB_TOKEN": "local-test-token"}), \
             patch.object(gate, "admit_original_runtime_phase10_output_record") as admit, \
             self.assertRaisesRegex(ValueError, "independent digest"):
            gate.main(args)
        admit.assert_not_called()
        args[args.index("--expected-original-producer-sha256") + 1] = sha256_bytes(producer_path.read_bytes())
        with patch.dict(os.environ, {"GITHUB_TOKEN": "local-test-token"}), \
             patch.object(gate, "admit_original_runtime_phase10_output_record",
                          return_value={"recordSha256": "sha256:" + "a" * 64,
                                        "recordPath": self.root / "admitted-record/signed-record/record.json"}) as admit, \
             redirect_stdout(StringIO()) as output:
            self.assertEqual(0, gate.main(args))
        self.assertEqual(producer, admit.call_args.kwargs["expected_producer"])
        self.assertEqual("sha256:" + "a" * 64, json.loads(output.getvalue())["recordSha256"])

    def test_independent_source_workflow_pgp_and_keyring_pins(self):
        for override in ({"trusted_source_commit": "0" * 40},
                         {"trusted_workflow_sha": "0" * 40},
                         {"expected_pgp_key_sha256": "sha256:" + "0" * 64}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.verify(**override)
        self.record["phase11Pins"]["expected_keyring_sha256"] = "sha256:" + "0" * 64
        self.sign()
        with self.assertRaisesRegex(ValueError, "verifier policy"):
            self.verify()

    def test_mutated_upload_signature_or_record_fails(self):
        self.record["officialUpload"]["artifact"]["id"] = 28
        self.sign()
        with self.assertRaisesRegex(ValueError, "official upload"):
            self.verify()
        self.record["officialUpload"] = deepcopy(self.upload)
        self.sign()
        self.signature.write_bytes(b"not a signature\n")
        with self.assertRaises(ValueError):
            self.verify()
        self.sign()
        self.record["unexpected"] = True
        self.sign()
        with self.assertRaisesRegex(ValueError, "fields are invalid"):
            self.verify()

    def test_wrong_candidate_identity_fails_even_with_valid_record_signature(self):
        self.record["officialUpload"]["captureProducer"]["commit"] = "0" * 40
        self.sign()
        with self.assertRaisesRegex(ValueError, "official upload"):
            self.verify()
        self.record["officialUpload"] = deepcopy(self.upload)
        self.record["phase11Pins"]["expected_validation_tree"] = "0" * 40
        self.sign()
        with self.assertRaisesRegex(ValueError, "validation checkout"):
            self.verify()

    def test_real_deep_verifier_rejects_signed_but_incomplete_runtime(self):
        # Transport/signature proof alone cannot admit a tree without actual
        # aggregate receipts, release attestation, and Maven PGP sidecars.
        with patch("ci.runtime_phase11_bytes._landed_tree", return_value=self.candidate_tree), \
             self.assertRaises((ValueError, OSError)):
            self.verify(deep=False)

    def test_signing_secret_rejects_before_signature_or_upload_access(self):
        with patch.dict(os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "forbidden"}), \
             patch.object(gate, "verify_manifest_signature") as signature, \
             patch.object(gate, "capture_observed_runtime_phase10_upload") as upload, \
             self.assertRaisesRegex(ValueError, "signing-secret"):
            gate.verify_signed_runtime_phase10_output_record(
                self.record_path, self.signature, self.repository, self.output,
                self.sidecars, self.pgp, self.plan,
                validation_repository=self.validation,
                trusted_source_commit=self.commit, trusted_workflow_sha="e" * 40,
                expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                token="local-test-token", environ={},
            )
        signature.assert_not_called()
        upload.assert_not_called()

    def test_signature_verifies_private_record_snapshot(self):
        original = gate.verify_manifest_signature
        record_bytes = self.record_path.read_bytes()
        signature_bytes = self.signature.read_bytes()
        def checked(record, signature, public, signing):
            self.assertNotEqual(self.record_path, record)
            self.assertNotEqual(self.signature, signature)
            self.assertEqual(record_bytes, record.read_bytes())
            self.assertEqual(signature_bytes, signature.read_bytes())
            return original(record, signature, public, signing)
        with patch.object(gate, "verify_manifest_signature", side_effect=checked):
            self.verify()

    def test_prepare_binds_official_upload_without_signing_or_mutating_runtime(self):
        destination = self.root / "prepared"
        output_before = regular_file_inventory(self.output, allow_empty=True)
        sidecars_before = regular_file_inventory(self.sidecars)

        def captured(_, __, capture, **kwargs):
            self.assertEqual(self.validation, Path(__))
            self.assertEqual(self.pins["expected_build_key"], kwargs["expected_build_key"])
            (capture / "original").mkdir(parents=True)
            shutil.copy2(self.output / "caller.json", capture / "original/caller.json")
            return deepcopy(self.upload)

        with patch.object(gate, "capture_observed_runtime_phase10_upload",
                          side_effect=captured), \
             patch.object(gate, "forward_verified_runtime_phase10_bytes") as deep:
            result = gate.prepare_runtime_phase10_output_record(
                self.plan, self.repository, self.output, self.sidecars, self.pgp,
                destination, phase11_pins=self.pins,
                validation_repository=self.validation,
                trusted_source_commit=self.commit, trusted_workflow_sha="e" * 40,
                expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                token="local-test-token", environ={},
            )
        self.assertEqual(self.record, result["record"])
        self.assertEqual(canonical_json_bytes(self.record),
                         (destination / "record.json").read_bytes())
        self.assertEqual(result["recordSha256"], sha256_bytes((destination / "record.json").read_bytes()))
        self.assertEqual(output_before, regular_file_inventory(self.output, allow_empty=True))
        self.assertEqual(sidecars_before, regular_file_inventory(self.sidecars))
        self.assertEqual(1, deep.call_count)
        self.assertNotEqual(self.output, deep.call_args.args[0])
        self.assertNotEqual(self.sidecars, deep.call_args.args[1])
        self.assertEqual(self.validation, deep.call_args.kwargs["landed_repository"])
        self.assertFalse((destination / "record.sig").exists())

    def test_prepare_rejects_unpinned_or_changed_input_before_publication(self):
        kwargs = dict(phase11_pins=self.pins, trusted_source_commit=self.commit,
                      validation_repository=self.validation,
                      trusted_workflow_sha="e" * 40,
                      expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                      token="local-test-token", environ={})
        destination = self.root / "prepared"
        with self.assertRaisesRegex(ValueError, "independent pins"):
            gate.prepare_runtime_phase10_output_record(
                self.plan, self.repository, self.output, self.sidecars, self.pgp,
                destination, **{**kwargs, "trusted_workflow_sha": "0" * 40},
            )
        (self.sidecars / "signature.asc").write_bytes(b"changed\n")
        with self.assertRaisesRegex(ValueError, "inventory"):
            gate.prepare_runtime_phase10_output_record(
                self.plan, self.repository, self.output, self.sidecars, self.pgp,
                destination, **kwargs,
            )
        self.assertFalse(destination.exists())

    def test_prepare_rejects_signing_secret_before_capture(self):
        with patch.dict(os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "forbidden"}), \
             patch.object(gate, "capture_observed_runtime_phase10_upload") as capture, \
             self.assertRaisesRegex(ValueError, "signing-secret"):
            gate.prepare_runtime_phase10_output_record(
                self.plan, self.repository, self.output, self.sidecars, self.pgp,
                self.root / "prepared", phase11_pins=self.pins,
                validation_repository=self.validation,
                trusted_source_commit=self.commit, trusted_workflow_sha="e" * 40,
                expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                token="local-test-token", environ={},
            )
        capture.assert_not_called()

    def test_isolated_signer_requires_source_policy_and_pinned_record(self):
        self.signature.unlink()
        digest = sha256_bytes(self.record_path.read_bytes())
        secret = {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": self.private.read_text()}
        with self.assertRaisesRegex(ValueError, "independent preparation"):
            signer.sign_prepared_runtime_phase10_record(
                self.record_path, self.repository, trusted_source_commit=self.commit,
                expected_record_sha256="sha256:" + "0" * 64, environ=secret,
            )
        self.assertFalse(self.signature.exists())
        result = signer.sign_prepared_runtime_phase10_record(
            self.record_path, self.repository, trusted_source_commit=self.commit,
            expected_record_sha256=digest, environ=secret,
        )
        self.assertEqual(digest, result["recordSha256"])
        self.assertEqual(result["signatureSha256"], sha256_bytes(self.signature.read_bytes()))
        self.assertEqual(self.record, self.verify())
        with self.assertRaisesRegex(ValueError, "already exists"):
            signer.sign_prepared_runtime_phase10_record(
                self.record_path, self.repository, trusted_source_commit=self.commit,
                expected_record_sha256=digest, environ=secret,
            )

    def test_publisher_forwards_exact_verified_pair(self):
        original_record = self.record_path.read_bytes()
        original_signature = self.signature.read_bytes()
        destination = self.root / "published-record"

        def captured(_, candidate, capture, **kwargs):
            self.assertEqual(self.validation, Path(candidate))
            (capture / "original").mkdir(parents=True)
            shutil.copy2(self.output / "caller.json", capture / "original/caller.json")
            return deepcopy(self.upload)

        with patch.object(gate, "capture_observed_runtime_phase10_upload", side_effect=captured), \
             patch.object(gate, "forward_verified_runtime_phase10_bytes") as deep:
            result = gate.publish_verified_runtime_phase10_output_record(
                self.record_path, self.signature, self.repository, self.validation,
                self.output, self.sidecars, self.pgp, self.plan, destination,
                expected_record_sha256=sha256_bytes(original_record),
                expected_signature_sha256=sha256_bytes(original_signature),
                trusted_source_commit=self.commit, trusted_workflow_sha="e" * 40,
                expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                token="local-test-token", environ={},
            )
        self.assertEqual(original_record, (destination / "record.json").read_bytes())
        self.assertEqual(original_signature, (destination / "record.sig").read_bytes())
        self.assertEqual(regular_file_inventory(destination), result["publishedFiles"])
        self.assertEqual(1, deep.call_count)

    def test_publisher_rejects_wrong_independent_pair_digest(self):
        with patch.object(gate, "capture_observed_runtime_phase10_upload") as capture, \
             self.assertRaisesRegex(ValueError, "independent Phase-10 pins"):
            gate.publish_verified_runtime_phase10_output_record(
                self.record_path, self.signature, self.repository, self.validation,
                self.output, self.sidecars, self.pgp, self.plan,
                self.root / "published-record",
                expected_record_sha256="sha256:" + "0" * 64,
                expected_signature_sha256=sha256_bytes(self.signature.read_bytes()),
                trusted_source_commit=self.commit, trusted_workflow_sha="e" * 40,
                expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                token="local-test-token", environ={},
            )
        capture.assert_not_called()

    def test_prepare_cli_rejects_unpinned_phase11_file_before_capture(self):
        pins_path = self.root / "phase11-pins.json"
        pins_path.write_bytes(canonical_json_bytes(self.pins))
        argv = [
            "prepare", "--plan", str(self.plan), "--repository-root", str(self.repository),
            "--validation-repository", str(self.validation),
            "--protected-output", str(self.output), "--maven-sidecars", str(self.sidecars),
            "--pgp-public-key", str(self.pgp), "--destination", str(self.root / "prepared"),
            "--phase11-pins", str(pins_path), "--expected-phase11-pins-sha256",
            "sha256:" + "0" * 64, "--trusted-source-commit", self.commit,
            "--trusted-workflow-sha", "e" * 40, "--expected-pgp-key-sha256",
            self.pins["expected_pgp_key_sha256"],
        ]
        with patch.dict(os.environ, {"GITHUB_TOKEN": "local-test-token"}), \
             patch.object(gate, "prepare_runtime_phase10_output_record") as prepare, \
             self.assertRaisesRegex(ValueError, "independent digest"):
            gate.main(argv)
        prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
