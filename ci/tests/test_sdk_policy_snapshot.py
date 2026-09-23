"""Caller policy pins include referenced bytes, not only descriptor JSON."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes
from ci import sdk_policy_snapshot as snapshot


snapshot_policy_closure = snapshot.snapshot_policy_closure


class SdkPolicySnapshotTest(unittest.TestCase):
    def test_apple_policy_tracks_transitive_evidence_and_rejects_symbolic_path(self):
        with tempfile.TemporaryDirectory(prefix="sdk-policy-snapshot-") as temporary:
            root = Path(temporary).resolve()
            fields = ("plan", "attestationPublicKey", "keyring", "keysDirectory",
                      "toolingEvidence", "toolingPublicKey", "javaExecutable")
            paths = {name: root / name for name in fields}
            for name, path in paths.items():
                if name in ("keysDirectory", "toolingEvidence"):
                    path.mkdir()
                    (path / "input.txt").write_text("original")
                else:
                    path.write_text("original")
            policy = {name: str(path) for name, path in paths.items()}
            policy.update(toolingKeyring=None, toolingKeysDirectory=None,
                          attestationTrustDomain="development", toolingTrustDomain="development")
            descriptor = root / "policy.json"
            descriptor.write_bytes(canonical_json_bytes(policy))
            first = snapshot_policy_closure("apple-validation", descriptor)
            (paths["toolingEvidence"] / "input.txt").write_text("changed")
            self.assertNotEqual(first, snapshot_policy_closure("apple-validation", descriptor))
            alias = root / "alias.json"
            alias.symlink_to(descriptor)
            with self.assertRaises(ValueError):
                snapshot_policy_closure("apple-validation", alias)

    def test_unknown_kind_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "policy.json"
            path.write_bytes(canonical_json_bytes({}))
            with self.assertRaisesRegex(ValueError, "Unsupported SDK caller policy kind"):
                snapshot_policy_closure("unreviewed", path)

    def test_core_policy_tracks_nested_facade_and_compatibility_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            descriptor = root / "core.json"
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": str(root / "evidence"),
                "records": [], "policy": {}}))
            evidence, capture, stage = (root / name for name in ("evidence", "capture", "stage"))
            for directory in (evidence, capture, stage):
                directory.mkdir()
                (directory / "input.txt").write_text("original")
            request, receipt, compatibility, nested = (root / name for name in
                ("request.json", "receipt.json", "compatibility.json", "nested.txt"))
            for path in (request, receipt, compatibility, nested):
                path.write_text("original")
            original = {"captureRoot": str(capture), "facadeRequest": str(request),
                        "validationReceipt": str(receipt)}
            with patch.object(snapshot, "core_arguments", return_value={"validations": {"jvm": original}}), \
                    patch.object(snapshot, "fresh_metadata_arguments", return_value={"validations": {"jvm": original}}), \
                    patch.object(snapshot, "facade_request", return_value=({"compatibilityRequest": str(compatibility)}, b"")), \
                    patch.object(snapshot, "facade_sources", return_value=({}, {"stage": stage}, {"receipt": receipt})), \
                    patch.object(snapshot, "_request_inventory", return_value={nested: "sha256:" + "a" * 64}):
                for kind in ("core-metadata", "core-metadata-fresh"):
                    nested.write_text("original")
                    first = snapshot_policy_closure(kind, descriptor)
                    nested.write_text("changed")
                    self.assertNotEqual(first, snapshot_policy_closure(kind, descriptor))
                descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": str(evidence),
                    "records": [{"receiptSha256": "sha256:" + "a" * 64}], "policy": {}}))
                with self.assertRaisesRegex(ValueError, "must not claim a metadata receipt"):
                    snapshot_policy_closure("core-metadata-fresh", descriptor)

    def test_android_policy_tracks_nested_contract_and_compatibility_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            descriptor = root / "android.json"
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": str(root / "evidence"),
                "records": [], "policy": {}}))
            evidence, contract = root / "evidence", root / "contract"
            for directory in (evidence, contract):
                directory.mkdir()
                (directory / "input.txt").write_text("original")
            compatibility, nested = root / "compatibility.json", root / "nested.txt"
            compatibility.write_text("original")
            nested.write_text("original")
            with patch.object(snapshot, "android_arguments", return_value={
                    "binary_contract_evidence": {}, "compatibility_request": compatibility}), \
                    patch.object(snapshot.sdk_android_validation_phase, "_contract_sources",
                                 return_value=({"contract": contract}, {})), \
                    patch.object(snapshot, "_request_inventory", return_value={nested: "sha256:" + "a" * 64}):
                first = snapshot_policy_closure("android-metadata", descriptor)
                (contract / "input.txt").write_text("changed")
                self.assertNotEqual(first, snapshot_policy_closure("android-metadata", descriptor))


if __name__ == "__main__":
    unittest.main()
