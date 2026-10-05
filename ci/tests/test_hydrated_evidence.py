"""Cache storage cannot manufacture qualified identities or portable trust."""
import os
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import patch

from ci.tests.test_runtime_original_ci import adapter  # Establish existing ci imports.
import hydrated_evidence as cache
from products.inventory import sha256_bytes


class HydratedEvidenceTest(unittest.TestCase):
    def test_expired_private_projection_rehydrates_but_changed_custody_rejects(self):
        # Local fixture and mocked native envelope authentication, not hosted evidence.
        from ci.tests.test_runtime_original_ci import RuntimeOriginalCiTest, TARGET
        from products.inventory import canonical_json_bytes, load_canonical_json_bytes, snapshot_regular_tree
        from products.restore import verification_session, _stage_fingerprint, verify_phase_shard
        from products.verified_evidence import _source_identity
        import reuse_qualification
        case = RuntimeOriginalCiTest()
        case.setUp()
        self.addCleanup(case.doCleanups)
        captured = case.root / "projection-seed"
        with patch("reuse.api_request", side_effect=case.api()), \
                patch.object(adapter, "download_artifact_to_file", side_effect=case.download_fixture):
            adapter.capture_runtime_original_ci_phases({"binary": case.receipts["binary"]}, captured,
                target=TARGET, trusted_workflow_sha=case.pin, token="not-a-real-token", recovery_projection=True)
        original = captured / "phases/binary/original"
        instance = adapter._identity(load_canonical_json_bytes(case.receipts["binary"].read_bytes()))
        verified = verify_phase_shard(original / "shard", instance)
        rows = load_canonical_json_bytes((captured / "transport/original-ci-phases.json").read_bytes())[
            "recoveryProjection"]["originalFiles"]["binary"]
        locator = {"fixture": "process-private custody lifetime"}
        key = canonical_json_bytes(locator)
        record = {"identity": {"locator": locator}, "receipt": verified["receipt"],
                  "receiptSha256": sha256_bytes(verified["receiptBytes"]),
                  "objectSha256": verified["objectSha256"], "originalFiles": rows}
        envelope, bundle = case.root / "fixture-qualification.json", case.root / "fixture-bundle.jsonl"
        envelope.write_bytes(b"fixture qualification; native authentication mocked\n")
        bundle.write_bytes(b"fixture signature, not genuine native authority\n")
        with patch.dict(os.environ, {"CODEX_AGENT_HYDRATED_EVIDENCE": str(case.root / "lifetime-cache")}), \
                verification_session() as session, \
                patch.object(reuse_qualification, "_authenticate_bytes",
                             return_value={"originals": [record]}) as authenticate:
            for row in rows:
                if not row["relativePath"].startswith("inputs/"):
                    cache.retain(row, original / row["relativePath"])
            session["portableQualificationInputs"] = dict(path=envelope, bundle=bundle,
                signer_commit="a" * 40, source_commit="b" * 40)
            for condition in ("mutated", "symlink", "expired"):
                with self.subTest(condition=condition):
                    with tempfile.TemporaryDirectory(dir=case.root) as temporary:
                        source = Path(temporary).resolve() / "projection/original"
                        snapshot_regular_tree(original, source, allow_empty=True)
                        witness = source, _stage_fingerprint(source.parent), rows, _source_identity()
                        session["qualifiedOriginalProjections"] = {key: witness}
                        self.assertEqual(witness, adapter._qualified_original_projection(locator))
                        if condition == "mutated":
                            (source / "shard/phase-receipt.json").write_bytes(b"changed")
                        elif condition == "symlink":
                            shutil.rmtree(source)
                            source.symlink_to(Path(temporary) / "missing", target_is_directory=True)
                        if condition != "expired":
                            with self.assertRaises(ValueError):
                                adapter._qualified_original_projection(locator)
                            authenticate.assert_not_called()
                    if condition == "expired":
                        self.assertFalse(source.exists())
                        restored = adapter._qualified_original_projection(locator)
                        authenticate.assert_called_once()
                        self.assertNotEqual(source, restored[0])
                        self.assertTrue(restored[0].is_relative_to(session["root"]))
                        self.assertEqual(verified["receipt"],
                                         verify_phase_shard(restored[0] / "shard", instance)["receipt"])
                        self.assertEqual(1, session["qualificationHits"])

    def test_restored_bytes_require_fresh_provenance_and_current_policy(self):
        from ci.tests.test_runtime_original_ci import RuntimeOriginalCiTest, TARGET
        from products.inventory import load_canonical_json_bytes, snapshot_regular_tree
        from products.restore import verification_session
        from runtime_reference_transport import stage_original_reference_handoff, resolve_original_reference_handoff
        case = RuntimeOriginalCiTest()
        case.setUp()
        self.addCleanup(case.doCleanups)
        with patch("reuse.api_request", side_effect=case.api()), \
                patch.object(adapter, "download_artifact_to_file", side_effect=case.download_fixture):
            captured = case.root / "initial-cold"
            adapter.capture_runtime_original_ci_phases({"binary": case.receipts["binary"]}, captured,
                target=TARGET, trusted_workflow_sha=case.pin, token="not-a-real-token", recovery_projection=True)
        receipt = load_canonical_json_bytes(case.receipts["binary"].read_bytes())
        prefix = f"product-resume-state/prior-failed-runtime/{TARGET}/binary/{TARGET}/phases/binary/original"
        source = {"relativePath": prefix, "kind": "phase", "receipt": receipt,
                  "artifactId": case.artifacts["binary"]["id"], "artifactSha256": case.artifacts["binary"]["digest"]}
        inputs = case.root / "inputs"
        snapshot_regular_tree(captured, inputs / f"product-resume-state/prior-failed-runtime/{TARGET}/binary/{TARGET}", allow_empty=True)
        (inputs / "product-resume-inputs").mkdir()
        (inputs / "product-resume-inputs/control.json").write_bytes(b"current authenticated envelope\n")
        thin = case.root / "thin"
        refs = stage_original_reference_handoff({name: inputs / name for name in
            ("product-resume-inputs", "product-resume-state")}, [source], thin)
        # Copy only raw bodies to the restored storage. Drop every private seal.
        shutil.rmtree(case.root / "persistent-cache")
        with patch.dict(os.environ, {"CODEX_AGENT_HYDRATED_EVIDENCE": str(case.root / "restored-storage")}):
            for row in refs["references"]:
                if row["source"] is not None:
                    cache.retain(row, inputs / row["relativePath"])
            for policy_changed in (False, True):
                restored = case.root / f"restored-{policy_changed}"
                snapshot_regular_tree(thin, restored, allow_empty=True)
                transports = []
                with verification_session() as session, patch("reuse.api_request", side_effect=case.api()) as requests, \
                        patch.object(adapter, "download_artifact_to_file", side_effect=case.download_fixture) as download:
                    def capture_source(source, rows, target):
                        transports.append(adapter._capture_runtime_original_reference_members(
                            {"event": "pull_request", "pullRequest": case.producer["pullRequest"],
                             "repository": case.producer["repository"]}, {**case.producer, "runId": 100},
                            source, rows, target, trusted_workflow_sha=case.pin, token="not-a-real-token"))
                    resolve_original_reference_handoff(restored, refs, capture_source)
                    adapter._register_qualified_original_projections(restored, refs, transports,
                                                                    trusted_workflow_sha=case.pin)
                    self.assertEqual(0, transports[0]["rangeBytes"])
                    if policy_changed:
                        # A witness from a different policy is never a hit.
                        session["qualifiedOriginalProjections"] = {
                            key: (*value[:3], "prior-policy") for key, value in
                            session["qualifiedOriginalProjections"].items()}
                    result = adapter.capture_runtime_original_ci_phases(
                        {"binary": restored / prefix / "shard/phase-receipt.json"},
                        case.root / f"replayed-{policy_changed}", target=TARGET,
                        trusted_workflow_sha=case.pin, token="not-a-real-token", recovery_projection=True)
                    cold_downloads = download.call_count + sum(call.args[0].endswith("/zip") for call in requests.call_args_list)
                    self.assertEqual(1 if policy_changed else 0, cold_downloads)
                    self.assertEqual(case.artifacts["binary"]["digest"], result["artifacts"]["binary"]["digest"])
                    if not policy_changed:
                        from products.registry import PhaseInstanceId
                        instance = PhaseInstanceId("runtime", TARGET, "binary", TARGET)
                        with patch("reuse.api_request", side_effect=case.api(run=case.failed_run())):
                            recovered = adapter.capture_prior_failed_runtime_phases(
                                {"event": "pull_request", "pullRequest": case.producer["pullRequest"],
                                 "repository": case.producer["repository"]}, {"runId": 100, "runAttempt": 1},
                                {instance: receipt["buildKey"]}, case.root / "qualified-discovery",
                                trusted_workflow_sha=case.pin, token="not-a-real-token", attempts=(case.failed_run(),))
                        self.assertEqual({instance}, set(recovered))
                        self.assertEqual(0, download.call_count)
                        _, artifact, raw, job = case.second_attempt_phase("binary", changed_output=True)
                        with patch("reuse.api_request", side_effect=case.two_attempt_api(
                                {"binary": artifact}, [job], {"binary": raw})), \
                                patch.object(adapter, "download_artifact_to_file",
                                             side_effect=lambda _artifact, _token, destination, **_options: destination.write_bytes(raw)), \
                                self.assertRaisesRegex(ValueError, "conflicting output inventories"):
                            adapter.capture_prior_failed_runtime_phases(
                                {"event": "pull_request", "pullRequest": case.producer["pullRequest"],
                                 "repository": case.producer["repository"]}, {"runId": 100, "runAttempt": 1},
                                {instance: receipt["buildKey"]}, case.root / "conflicting-qualified-discovery",
                                trusted_workflow_sha=case.pin, token="not-a-real-token",
                                attempts=(case.failed_run(), case.failed_run(72, 3)))
                    with patch("products.verified_evidence._source_identity", return_value="changed-live-policy"), \
                            self.assertRaisesRegex(ValueError, "policy changed"):
                        adapter.capture_runtime_original_ci_phases(
                            {"binary": restored / prefix / "shard/phase-receipt.json"},
                            case.root / f"changed-live-{policy_changed}", target=TARGET,
                            trusted_workflow_sha=case.pin, token="not-a-real-token", recovery_projection=True)
            changed_job = [{**job, "conclusion": "failure"} for job in case.jobs]
            with patch("reuse.api_request", side_effect=case.api(jobs=changed_job)), self.assertRaises(ValueError):
                adapter._capture_runtime_original_reference_members(
                    {"event": "pull_request", "pullRequest": case.producer["pullRequest"],
                     "repository": case.producer["repository"]}, {**case.producer, "runId": 100}, source,
                    [row for row in refs["references"] if row["source"] == prefix], case.root / "wrong-provenance",
                    trusted_workflow_sha=case.pin, token="not-a-real-token")

    def test_miss_hit_tamper_and_wrong_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.dict(os.environ, {"CODEX_AGENT_HYDRATED_EVIDENCE": str(root / "cache")}):
                source = root / "original"
                source.write_bytes(b"preserved immutable bytes")
                record = {"bytes": source.stat().st_size, "sha256": sha256_bytes(source.read_bytes())}
                self.assertFalse(cache.copy(record, root / "missing"))
                cache.retain(record, source)
                self.assertTrue(cache.copy(record, root / "restored"))
                self.assertEqual(source.read_bytes(), (root / "restored").read_bytes())
                self.assertFalse(cache.copy({**record, "sha256": "sha256:" + "0" * 64}, root / "wrong"))
                cache.blob(record).write_bytes(b"tampered")
                with self.assertRaises(ValueError):
                    cache.copy(record, root / "tampered")
                with self.assertRaises(ValueError):
                    cache.retain(record, source)
                self.assertEqual(b"preserved immutable bytes", source.read_bytes())

    def test_restored_symlinks_never_enter_trust(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.dict(os.environ, {"CODEX_AGENT_HYDRATED_EVIDENCE": str(root / "cache")}):
                source = root / "original"
                source.write_bytes(b"immutable")
                record = {"bytes": 9, "sha256": sha256_bytes(b"immutable")}
                blob = cache.blob(record)
                blob.parent.mkdir(parents=True)
                blob.symlink_to(source)
                with self.assertRaises(ValueError):
                    cache.copy(record, root / "restored")
                blob.unlink()
                blob.parent.rmdir()
                outside = root / "outside"
                outside.mkdir()
                blob.parent.symlink_to(outside, target_is_directory=True)
                with self.assertRaises(ValueError):
                    cache.retain(record, source)
                self.assertEqual([], list(outside.iterdir()))


if __name__ == "__main__":
    unittest.main()
