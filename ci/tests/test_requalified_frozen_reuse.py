"""Requalification trust-boundary checks; synthetic origins are not CI acceptance."""
import copy
from contextlib import contextmanager
import io
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import product_reuse as products
import reuse_qualification as issuer
import reuse_qualification as qualification
from products.inventory import canonical_json_bytes, sha256_bytes, write_canonical_json
from products.signatures import generate_development_key, sign_manifest
from ci.tests import test_completed_frozen_reuse as fixtures


class RequalifiedFrozenReuseTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompletedFrozenReuseTest()
        self.fixture.setUp()

    def test_native49_delegation_preserves_originals_and_rejects_changed_identity(self):
        parent = copy.deepcopy(self.fixture.qualified)
        parent.update(schemaVersion=1, sourceCommit="a" * 40)
        for index, row in enumerate(parent["originals"]):
            row["identity"] = {"policy": fixtures.POLICY, "locator": {
                "instance": products._identity_record(products._identity(row["receipt"])),
                "workflowSha": "a" * 40, "artifact": {"id": index + 1}, "job": {"id": index + 1}}}
        cap = qualification.CompletedFrozenReuse(self.fixture.spec, self.fixture.receipts.values(),
            qualification._COMPLETED_FROZEN, revision="d" * 40, originals=parent["originals"])
        cap._eligible = frozenset(set(cap.completed_phases()) - {issuer._REQUALIFIED_AGGREGATE})
        policy = "sha256:" + "b" * 64
        aggregate = copy.deepcopy(next(row for row in parent["originals"]
            if products._identity(row["receipt"]) == issuer._REQUALIFIED_AGGREGATE))
        aggregate["identity"]["policy"] = policy
        current = {"schemaVersion": 1, "sourceCommit": "b" * 40,
                   "verifierPolicySha256": policy, "originals": [aggregate]}
        before = canonical_json_bytes(parent)
        result = issuer._inherit_requalified_originals(parent, cap, current, policy=policy)
        self.assertEqual(before, canonical_json_bytes(parent))
        self.assertEqual(46, len(result["originals"]))
        for row in result["originals"]:
            original = next(old for old in parent["originals"] if old["receipt"] == row["receipt"])
            self.assertEqual({k: v for k, v in original.items() if k != "identity"},
                             {k: v for k, v in row.items() if k != "identity"})
            self.assertEqual(original["identity"]["locator"], row["identity"]["locator"])
        changed = copy.deepcopy(parent)
        changed["originals"][0]["objectSha256"] = policy
        with self.assertRaises(ValueError):
            issuer._inherit_requalified_originals(changed, cap, current, policy=policy)
        changed = copy.deepcopy(parent)
        changed["originals"][0]["identity"]["locator"]["artifact"]["id"] += 1000
        with self.assertRaisesRegex(ValueError, "locator"):
            issuer._inherit_requalified_originals(changed, cap, current, policy=policy)
        changed = copy.deepcopy(parent)
        changed["originals"][0]["originalFiles"][0]["bytes"] += 1
        with self.assertRaisesRegex(ValueError, "member inventory"):
            issuer._inherit_requalified_originals(changed, cap, current, policy=policy)
        cap._eligible = frozenset(list(cap._eligible)[1:])
        with self.assertRaisesRegex(ValueError, "native49"):
            issuer._inherit_requalified_originals(parent, cap, current, policy=policy)
        with self.assertRaisesRegex(ValueError, "concrete"):
            issuer._inherit_requalified_originals(parent, object(), current, policy=policy)

    def test_first_sdk_checkpoint_accepts_only_exact_fifty_plus_ios(self):
        sdk, _, _, _ = self.fixture.sdk_fixture()
        controls = sdk["proof"]["controls"]
        request = controls["product-resume-state/reuse-wave-request.json"]
        result = controls["product-resume-state/reuse-wave-result.json"]
        request["availableObjects"] = [row for row in request["availableObjects"] if row["component"] != "javascript"]
        result["phases"] = [row for row in result["phases"] if row["component"] != "javascript"]
        sdk["spec"]["retainedPhaseCount"] = 51
        def update_controls():
            sdk["spec"]["controls"] = [{"relativePath": path, "bytes": len(canonical_json_bytes(value)),
                "sha256": sha256_bytes(canonical_json_bytes(value))} for path, value in controls.items()]
        def check():
            return qualification._completed_sdk_controls(sdk["spec"], controls, self.fixture.spec, sdk["original"])
        update_controls()
        self.assertEqual(51, len(check()[0]["availableObjects"]))
        for wrong in (True, 50, 53):
            sdk["spec"]["retainedPhaseCount"] = wrong
            with self.assertRaises(ValueError):
                check()
        sdk["spec"]["retainedPhaseCount"] = 51
        result["phases"][-1] = {**result["phases"][-1], "component": "javascript", "phase": "package", "target": "node"}
        update_controls()
        with self.assertRaisesRegex(ValueError, "unrelated phases"):
            check()

    def test_successor_selection_uses_pinned_git_and_ignores_working_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            def git(*args):
                return subprocess.check_output(["git", "-C", str(root), "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", *args], stderr=subprocess.DEVNULL, text=True).strip()
            git("init")
            old = root / "ci/tests/data/hosted-frozen-reuse.json"
            old.parent.mkdir(parents=True)
            old.write_text("{}\n")
            git("add", ".")
            git("commit", "-m", "historical fixture")
            before = git("rev-parse", "HEAD")
            (root / issuer._REQUALIFIED_FROZEN_SPEC).write_text("{}\n")
            self.assertEqual(old.relative_to(root).as_posix(), qualification._frozen_spec_path(root, before))
            git("add", ".")
            git("commit", "-m", "fixed successor")
            after = git("rev-parse", "HEAD")
            self.assertEqual(issuer._REQUALIFIED_FROZEN_SPEC, qualification._frozen_spec_path(root, after))
            self.assertEqual(old.relative_to(root).as_posix(), qualification._frozen_spec_path(root, before))

    def test_sdk_planner_source_requires_exact_successful_job_and_transport_size(self):
        sdk, _, _, _ = self.fixture.sdk_fixture()
        spec = sdk["spec"]
        spec["sourceRole"] = "plan"
        job = {"name": "product-validation / plan", "id": spec["jobId"]}
        artifact = {"size_in_bytes": spec["artifactBytes"]}
        with patch.object(products, "_observe_ci_producer_jobs", return_value=[{"run": {}, "jobs": [job]}]) as observe, \
                patch.object(products, "_contract_ci_upload_metadata", return_value=artifact) as metadata, \
                patch.object(products, "_require_artifact_job_window") as window, \
                patch.object(products, "_runtime_original_locator", return_value={}) as locator:
            qualification._observe_completed_sdk_resume(spec, "fixture")
            self.assertEqual({"resume": "product-validation / plan"}, observe.call_args.kwargs["jobs_by_phase"])
            self.assertEqual(f"codex-agent-planned-product-resume-{spec['producer']['tree']}", metadata.call_args.args[2])
            window.assert_called_once_with({"run": {}, "jobs": [job]}, "product-validation / plan", artifact)
            locator.assert_called_once()
            with self.assertRaisesRegex(ValueError, "successful job"):
                qualification._observe_completed_sdk_resume({**spec, "jobId": spec["jobId"] + 1}, "fixture")
            with self.assertRaisesRegex(ValueError, "transport size"):
                qualification._observe_completed_sdk_resume({**spec, "artifactBytes": spec["artifactBytes"] + 1}, "fixture")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                qualification._observe_completed_sdk_resume({**spec, "sourceRole": "any-success"}, "fixture")

    def test_native_frozen_contract_controls_require_exact_receipts_and_full_member_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.fixture.contract_stage_fixture(root)
            receipts = [receipt for instance, receipt in self.fixture.receipts.items() if instance.product == "contract"]
            self.fixture.proof["contractReceipts"] = receipts
            self.fixture.proof["resultSha256"] = sha256_bytes(canonical_json_bytes(self.fixture.spec["expectedResult"]))
            def fetch(name, **kwargs):
                destination = root / name
                destination.mkdir()
                return self.fixture.fetched(destination, **kwargs)
            cap, report = fetch("native")
            self.assertEqual(0, report["productBodiesDownloaded"])
            self.assertIsNotNone(cap._contract)
            changed = copy.deepcopy(self.fixture.proof)
            changed["contractReceipts"][0]["outputs"][0]["sha256"] = "sha256:" + "e" * 64
            with self.assertRaises(ValueError):
                fetch("changed", proof=changed)
            changed = copy.deepcopy(self.fixture.proof)
            changed["contractReceipts"] = [receipts[0]] * 4
            with self.assertRaises(ValueError):
                fetch("duplicate", proof=changed)
            original = self.fixture.qualified["originals"][0]
            original["originalFiles"] = [row for row in original["originalFiles"]
                if not row["relativePath"].endswith("stage/output-manifest.json")]
            with self.assertRaisesRegex(ValueError, "coverage"):
                fetch("missing-coverage")

    def test_checkpoint_requires_real_signature_current_receipt_payload_and_public_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private, public, metadata = generate_development_key(root / "fixture-key")
            signing = {**metadata, "trustDomain": "release", "keyId": "release-fixture"}
            keys = root / "gradle/release/keys"
            keys.mkdir(parents=True)
            (keys / "release-fixture.pub").write_bytes(public.read_bytes())
            policy = {"schemaVersion": 1, "namespace": signing["namespace"], "algorithm": signing["algorithm"],
                "trustDomain": "release", "activeKey": {"keyId": signing["keyId"],
                    "fingerprint": signing["fingerprint"]}, "retiredKeys": []}
            write_canonical_json(keys.parent / "product-signing-keys.json", policy)
            original = root / "original/aggregate-input"
            original.mkdir(parents=True)
            payload = original / "codex-agent-runtime-0.8.0-manifest.json"
            payload.write_bytes(b"{}\n")
            attestation = original / "codex-agent-runtime-0.8.0.attestation.json"
            value = {"signing": signing, "metadataReceiptSha256": fixtures.POLICY,
                "payload": {"fileName": payload.name, "bytes": payload.stat().st_size,
                            "sha256": sha256_bytes(payload.read_bytes())}}
            write_canonical_json(attestation, value)
            signature = sign_manifest(attestation, private, signing)
            signature.rename(original / "codex-agent-runtime-0.8.0.attestation.sig")
            source = {"producer": {"tree": "a" * 40, "runAttempt": 1}, "workflowSha": "b" * 40,
                      "artifactId": 71, "artifactSha256": fixtures.POLICY}
            spec = {"request": {"versions": {"runtime-release": "0.8.0"}},
                "requalification": {"signedSource": source}, "expectedResult": {"phases": [
                    {**products._identity_record(issuer._REQUALIFIED_AGGREGATE), "receiptSha256": fixtures.POLICY}]}}
            archive_bytes = b""
            def repackage():
                nonlocal archive_bytes
                members = sorted(original.iterdir())
                spec["signedCheckpoint"] = [{"relativePath": "aggregate-input/" + path.name,
                    "bytes": path.stat().st_size, "sha256": sha256_bytes(path.read_bytes())} for path in members]
                raw = io.BytesIO()
                with zipfile.ZipFile(raw, "w") as archive:
                    for path in members:
                        archive.writestr("aggregate-input/" + path.name, path.read_bytes())
                archive_bytes = raw.getvalue()
            @contextmanager
            def opened(*args, **kwargs):
                with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                    yield archive, SimpleNamespace(transferred=len(archive_bytes))
            repackage()
            with patch.object(products, "_observe_ci_producer_jobs", return_value=[{"run": {}}]), \
                    patch.object(products, "_contract_ci_upload_metadata", return_value={}), \
                    patch.object(products, "_require_artifact_job_window"), \
                    patch("runtime_reference_archive.open_reference_archive", side_effect=opened):
                self.assertEqual(len(archive_bytes), issuer._requalified_signed_checkpoint(spec, root / "valid", root, "fixture"))
                payload.write_bytes(b'{"changed":true}\n')
                repackage()
                with self.assertRaisesRegex(ValueError, "receipt/payload"):
                    issuer._requalified_signed_checkpoint(spec, root / "bad-payload", root, "fixture")
                payload.write_bytes(b"{}\n")
                spec["expectedResult"]["phases"][0]["receiptSha256"] = "sha256:" + "c" * 64
                repackage()
                with self.assertRaisesRegex(ValueError, "receipt/payload"):
                    issuer._requalified_signed_checkpoint(spec, root / "bad-receipt", root, "fixture")
                spec["expectedResult"]["phases"][0]["receiptSha256"] = fixtures.POLICY
                value["metadataReceiptSha256"] = "sha256:" + "d" * 64
                write_canonical_json(attestation, value)
                repackage()
                with self.assertRaisesRegex(ValueError, "SSHSIG"):
                    issuer._requalified_signed_checkpoint(spec, root / "bad-signature", root, "fixture")
                value["metadataReceiptSha256"] = fixtures.POLICY
                write_canonical_json(attestation, value)
                policy["activeKey"] = None
                write_canonical_json(keys.parent / "product-signing-keys.json", policy)
                repackage()
                with self.assertRaises(ValueError):
                    issuer._requalified_signed_checkpoint(spec, root / "bad-key", root, "fixture")


if __name__ == "__main__":
    unittest.main()
