"""Synthetic stopgates for the offline Runtime candidate semantic join."""

from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from ci import runtime_candidate_join as candidate
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file
from ci.tests.test_runtime_candidate_transport import _selection


_A, _B, _C = "a" * 40, "b" * 40, "c" * 40
_KEY, _RECEIPT, _MANIFEST = ("sha256:" + char * 64 for char in "123")


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value) if type(value) is dict else value)


def _zip(path, source):
    with ZipFile(path, "w") as archive:
        for member in source.rglob("*"):
            if member.is_file():
                archive.write(member, member.relative_to(source).as_posix())


class RuntimeCandidateJoinTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-join-test-", dir=Path.cwd())
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.transports = self.root / "transports"
        self.aggregate = self.root / "aggregate"
        self.sidecar = self.root / "sidecar"
        self.trusted = self.root / "trusted"
        self.validation = self.root / "validation"
        self.landed = self.root / "landed"
        self.policy = self.root / "policy"
        self.output = self.root / "candidate"
        for path in (self.transports, self.aggregate, self.sidecar, self.trusted,
                     self.validation, self.landed, self.policy / "keys"):
            path.mkdir(parents=True)
        self.keyring = self.policy / "product-signing-keys.json"
        self.keys = self.policy / "keys"
        self.pgp = self.root / "pgp.asc"
        _write(self.keyring, b"keyring\n")
        _write(self.keys / "release.pub", b"release-key\n")
        _write(self.pgp, b"pgp-key\n")
        self.selection = _selection()
        self.selection["catalog"]["producer"]["tree"] = _B
        self.selection["phase10"]["originalProducer"]["tree"] = _B
        self.phase11 = {"expected_protected_inventory_sha256": "",
            "expected_sidecar_inventory_sha256": "", "expected_metadata_receipt_sha256": _RECEIPT,
            "expected_build_key": _KEY, "expected_runtime_version": "0.8.0",
            "expected_manifest_sha256": _MANIFEST, "expected_source_commit": _C,
            "expected_source_tree": _B, "expected_validation_tree": _B,
            "expected_workflow_sha": _C,
            "expected_keyring_sha256": sha256_file(self.keyring),
            "expected_keys_inventory_sha256": candidate._digest_tree(self.keys),
            "expected_pgp_key_sha256": sha256_file(self.pgp)}
        plan = b"{}\n"
        for capture in (self.aggregate, self.sidecar):
            _write(capture / "plan/impact-plan.json", plan)
        _write(self.aggregate / "original/retained-release/proof.txt", b"original\n")
        _write(self.sidecar / "original/signature.asc", b"sidecar\n")
        self.phase11["expected_protected_inventory_sha256"] = candidate._digest_tree(
            self.aggregate / "original", allow_empty=True)
        self.phase11["expected_sidecar_inventory_sha256"] = candidate._digest_tree(
            self.sidecar / "original")
        _zip(self.aggregate / "transport.zip", self.aggregate / "original")
        _zip(self.sidecar / "transport.zip", self.sidecar / "original")
        self.aggregate_control = {"artifact": {"id": 40,
            "digest": sha256_file(self.aggregate / "transport.zip")},
            "captureProducer": self.selection["phase10"]["originalProducer"],
            "observed": [], "aggregateBuildKey": _KEY,
            "aggregateReceiptSha256": _RECEIPT}
        sidecar_control = {"artifact": {"id": 41,
            "digest": sha256_file(self.sidecar / "transport.zip")},
            "producer": self.selection["phase10"]["originalProducer"],
            "observation": {}, "trustedWorkflowPath": ".github/workflows/runtime-phase10-maven.yml",
            "trustedWorkflowSha": _C, "trustedJobName": "runtime-phase10-maven",
            "planArtifactId": 42, "planArtifactSha256": _MANIFEST,
            "planSha256": sha256_bytes(plan), "sidecarFiles":
                regular_file_inventory(self.sidecar / "original")}
        _write(self.aggregate / "capture-transport.json", self.aggregate_control)
        _write(self.sidecar / "capture-transport.json", sidecar_control)
        self.pins = {"phase11Pins": self.phase11,
            "transportInventorySha256": "", "aggregateCaptureInventorySha256":
                candidate._digest_tree(self.aggregate),
            "sidecarCaptureInventorySha256": candidate._digest_tree(self.sidecar),
            "aggregateArtifactId": 40, "aggregateArtifactSha256":
                self.aggregate_control["artifact"]["digest"],
            "sidecarArtifactId": 41, "sidecarArtifactSha256":
                sidecar_control["artifact"]["digest"],
            "originalPlanSha256": sha256_bytes(plan), "planArtifactId": 42,
            "planArtifactSha256": _MANIFEST, "aggregateWorkflowSha": _C,
            "sidecarWorkflowSha": _C}
        catalog = self.transports / "catalog"
        _write(catalog / "catalog/product-index.json", b"index\n")
        _write(catalog / "catalog/product-index.sig", b"index-sig\n")
        _write(catalog / "catalog/runtime-aggregate-release-evidence/handoffs/original/proof.txt",
               b"original\n")
        _write(catalog / "caller.json", {"producer": self.selection["catalog"]["producer"],
            "originalProducer": self.selection["phase10"]["originalProducer"],
            "validatedTree": _B, "aggregateBuildKey": _KEY,
            "aggregateReceiptSha256": _RECEIPT, "originalUploadArtifactId": 40,
            "originalUploadSha256": self.pins["aggregateArtifactSha256"],
            "trustedWorkflowSha": _C})
        _zip(self.transports / "catalog.zip", catalog)
        record = {"schemaVersion": 1, "product": "runtime", "signing":
            {"algorithm": "ed25519", "namespace": "test", "trustDomain": "release",
             "keyId": "test"}, "trustedSourceCommit": _C,
            "officialUpload": self.aggregate_control, "phase11Pins": self.phase11,
            "protectedFiles": regular_file_inventory(self.aggregate / "original"),
            "sidecarFiles": regular_file_inventory(self.sidecar / "original")}
        self.record_path = self.transports / "phase10-record/record.json"
        _write(self.record_path, record)
        _write(self.transports / "phase10-record/record.sig", b"record-sig\n")
        _zip(self.transports / "phase10-record.zip", self.transports / "phase10-record")
        self.selection["catalog"].update({"artifactId": 30,
            "artifactSha256": sha256_file(self.transports / "catalog.zip"),
            "inventorySha256": candidate._digest_tree(catalog),
            "indexSha256": sha256_file(catalog / "catalog/product-index.json"),
            "signatureSha256": sha256_file(catalog / "catalog/product-index.sig")})
        self.selection["phase10"].update({"artifactId": 31,
            "artifactSha256": sha256_file(self.transports / "phase10-record.zip"),
            "recordSha256": sha256_file(self.record_path),
            "signatureSha256": sha256_file(self.transports / "phase10-record/record.sig")})
        routes = {label: {"producer": producer,
            "artifact": {"id": selected["artifactId"], "digest": selected["artifactSha256"]},
            "files": regular_file_inventory(self.transports / label)}
            for label, selected, producer in (
                ("catalog", self.selection["catalog"], self.selection["catalog"]["producer"]),
                ("phase10-record", self.selection["phase10"],
                 self.selection["phase10"]["recordProducer"]))}
        _write(self.transports / "transport.json", {"schemaVersion": 1,
            "selectionSha256": sha256_bytes(canonical_json_bytes(self.selection)), "routes": routes})
        self.pins["transportInventorySha256"] = candidate._digest_tree(self.transports)
        self.index = {"repository": candidate.transport.REPOSITORY if hasattr(
            candidate.transport, "REPOSITORY") else "codex-agent-labs/codex-agent",
            "producer": self.selection["catalog"]["producer"],
            "trustDomain": "release", "context": {"kind": "promoted-main", "tree": _B},
            "entries": [{"product": "runtime", "component": "runtime-aggregate",
                "phase": "metadata", "target": "aggregate", "buildKey": _KEY,
                "receiptSha256": _RECEIPT, "artifactSha256": _MANIFEST,
                "productVersion": "0.8.0"}]}

    def run_join(self, *, selection=None, pins=None, side_effect=None, aggregate=None, sidecar=None, cli=False):
        selected = self.selection if selection is None else selection
        approved = self.pins if pins is None else pins
        def forward(*args, **kwargs):
            target = args[2]
            _write(target / "runtime-release/original.txt", b"forwarded\n")
            if side_effect:
                side_effect()
            return {"product": "runtime", "runtimeVersion": "0.8.0"}
        policy = SimpleNamespace(keyring=self.keyring, keys=self.keys)
        with patch.object(candidate.transport, "_validate_plan", return_value={
                "remoteBuildAuthorized": True}), \
             patch.object(candidate.transport, "_consumer", return_value={
                 "producer": self.selection["phase10"]["originalProducer"]}), \
             patch.object(candidate.transport, "_release_trust", return_value=policy), \
             patch.object(candidate.transport, "_git_value", side_effect=lambda *args:
                          _B if "^{tree}" in args[-1] else _A), \
             patch.object(candidate, "_landed_tree", return_value=_B), \
             patch.object(candidate, "load_keyring", return_value={
                 "algorithm": "ed25519", "namespace": "test", "trustDomain": "release"}), \
             patch.object(candidate, "require_active_release_key", return_value=(
                 {"keyId": "test"}, self.keys / "release.pub")), \
             patch.object(candidate, "verify_manifest_signature"), \
             patch.object(candidate, "verify_release_product_index", return_value=(self.index, b"index\n")), \
             patch.object(candidate, "load_runtime_aggregate_release_evidence", return_value=[{
                 "receiptSha256": _RECEIPT, "handoffRoot": "handoffs/original"}]), \
             patch.object(candidate, "_original_carrier", return_value=
                 self.aggregate / "original/retained-release"), \
             patch.object(candidate.transport, "stage_release_catalog"), \
             patch.object(candidate, "forward_verified_runtime_phase10_bytes", side_effect=forward) as forwarder:
            if cli:
                _write(self.root / "selection.json", selected)
                _write(self.root / "pins.json", approved)
                arguments = []
                for name, path in (("selection", self.root / "selection.json"),
                    ("pins", self.root / "pins.json"), ("transports", self.transports),
                    ("trusted-repository", self.trusted), ("validation-repository", self.validation),
                    ("landed-repository", self.landed), ("pgp-public-key", self.pgp),
                    ("destination", self.output)):
                    arguments.extend(["--" + name, str(path)])
                arguments.extend(["--expected-selection-sha256", sha256_bytes(canonical_json_bytes(selected)),
                                  "--expected-pins-sha256", sha256_bytes(canonical_json_bytes(approved))])
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(0, candidate.main(arguments))
                return json.loads(output.getvalue()), forwarder
            result = candidate.join_runtime_candidate(selected, approved,
                self.transports, aggregate or self.aggregate, sidecar or self.sidecar, self.trusted,
                self.validation, self.landed, self.pgp, self.output,
                expected_selection_sha256=sha256_bytes(canonical_json_bytes(selected)),
                expected_pins_sha256=sha256_bytes(canonical_json_bytes(approved)))
            return result, forwarder

    def test_joins_exact_original_and_forwards_only_after_checks(self):
        result, forward = self.run_join()
        self.assertEqual("runtime", result["candidate"]["product"])
        self.assertEqual(b"forwarded\n", (self.output / "runtime-release/original.txt").read_bytes())
        forward.assert_called_once()

    def test_rejects_changed_record_or_original_before_forward(self):
        bad = copy.deepcopy(self.pins)
        bad["aggregateArtifactSha256"] = _KEY
        with self.assertRaisesRegex(ValueError, "selected original upload"):
            self.run_join(pins=bad)
        self.assertFalse(self.output.exists())
        bad = copy.deepcopy(self.pins)
        bad["phase11Pins"]["expected_build_key"] = _MANIFEST
        with self.assertRaisesRegex(ValueError, "original captures disagree|signed Phase-10 record"):
            self.run_join(pins=bad)
        self.assertFalse(self.output.exists())

    def test_rejects_late_mutation_before_publication(self):
        def mutate():
            _write(self.transports / "catalog/caller.json", b"changed\n")
        with self.assertRaisesRegex(ValueError, "changed before final publication"):
            self.run_join(side_effect=mutate)
        self.assertFalse(self.output.exists())

    def retained_captures(self):
        retained = self.transports / "catalog/original-evidence"
        shutil.copytree(self.aggregate / "original", retained / "original")
        shutil.copyfile(self.aggregate / "transport.zip", retained / "upload.zip")
        shutil.copytree(self.sidecar, self.transports / "sidecar-capture")
        _zip(self.transports / "sidecar-capture.zip", self.transports / "sidecar-capture")
        _zip(self.transports / "catalog.zip", self.transports / "catalog")
        self.selection["schemaVersion"] = 2
        self.selection["phase10"]["sidecarTransport"] = {"artifactId": 43,
            "artifactSha256": sha256_file(self.transports / "sidecar-capture.zip")}
        self.selection["catalog"]["artifactSha256"] = sha256_file(self.transports / "catalog.zip")
        self.selection["catalog"]["inventorySha256"] = candidate._digest_tree(self.transports / "catalog")
        custody = json.loads((self.transports / "transport.json").read_bytes())
        custody["schemaVersion"] = 2
        custody["selectionSha256"] = sha256_bytes(canonical_json_bytes(self.selection))
        custody["routes"]["catalog"]["files"] = regular_file_inventory(self.transports / "catalog")
        custody["routes"]["catalog"]["artifact"]["digest"] = self.selection["catalog"]["artifactSha256"]
        custody["routes"]["sidecar-capture"] = {
            "producer": self.selection["phase10"]["recordProducer"],
            "artifact": {"id": 43, "digest": self.selection["phase10"]["sidecarTransport"]["artifactSha256"]},
            "files": regular_file_inventory(self.transports / "sidecar-capture")}
        _write(self.transports / "transport.json", custody)
        self.pins["transportInventorySha256"] = candidate._digest_tree(self.transports)
        return retained

    def test_retained_capture_preserves_bytes_and_provenance_without_body_copy(self):
        retained = self.retained_captures()
        before = regular_file_inventory(self.transports)
        view = candidate._catalog_capture(self.transports, self.root / "view", self.pins)
        for source, target in ((retained / "upload.zip", view / "transport.zip"),
                               (retained / "original/retained-release/proof.txt",
                                view / "original/retained-release/proof.txt")):
            self.assertEqual(source.stat().st_ino, target.stat().st_ino)
        self.assertEqual((self.aggregate / "capture-transport.json").read_bytes(),
                         (view / "capture-transport.json").read_bytes())
        result, forward = self.run_join(aggregate=view, sidecar=self.transports / "sidecar-capture")
        self.assertEqual("runtime", result["candidate"]["product"])
        forward.assert_called_once()
        self.assertEqual(before, regular_file_inventory(self.transports))

    def test_retained_capture_rejects_changed_original_and_symlink(self):
        retained = self.retained_captures()
        original = retained / "original/retained-release/proof.txt"
        original.write_bytes(b"tampered\n")
        with self.assertRaisesRegex(ValueError, "independently approved original capture"):
            candidate._catalog_capture(self.transports, self.root / "bad-view", self.pins)
        original.unlink()
        original.symlink_to(self.aggregate / "original/retained-release/proof.txt")
        with self.assertRaises(ValueError):
            candidate._catalog_capture(self.transports, self.root / "symlink-view", self.pins)
        self.assertFalse((self.root / "symlink-view").exists())

    def test_cli_joins_retained_captures_without_explicit_recapture(self):
        self.retained_captures()
        before = regular_file_inventory(self.transports)
        result, forward = self.run_join(cli=True)
        self.assertEqual("runtime", result["candidate"]["product"])
        forward.assert_called_once()
        self.assertEqual(before, regular_file_inventory(self.transports))
        self.assertFalse(list(self.root.glob("runtime-original-view-*")))


if __name__ == "__main__":
    unittest.main()
