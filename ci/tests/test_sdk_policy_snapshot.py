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

    def test_fresh_core_bootstrap_pins_raw_policy_and_typed_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            policy, nested = root / "policy.json", root / "native.tar.gz"
            policy.write_bytes(canonical_json_bytes({"validations": "caller-selected"}))
            nested.write_bytes(b"first")
            def sources(_policy):
                return {nested: snapshot.sha256_file(nested)}, {}
            with patch("ci.sdk_facade_original_inputs._fresh_policy_sources", side_effect=sources):
                first = snapshot_policy_closure("core-metadata-bootstrap", policy)
                nested.write_bytes(b"second")
                self.assertNotEqual(first, snapshot_policy_closure("core-metadata-bootstrap", policy))
                policy.write_bytes(canonical_json_bytes({"validations": "changed"}))
                self.assertNotEqual(first, snapshot_policy_closure("core-metadata-bootstrap", policy))
                before = snapshot._snapshot
                def mutate(paths):
                    value = before(paths)
                    nested.write_bytes(b"changed-after-snapshot")
                    return value
                with patch.object(snapshot, "_snapshot", side_effect=mutate), self.assertRaisesRegex(
                        ValueError, "changed during snapshot"):
                    snapshot_policy_closure("core-metadata-bootstrap", policy)
                nested.write_bytes(b"stable")
                calls = 0
                def aba(paths):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        nested.write_bytes(b"transient")
                        value = before(paths)
                        nested.write_bytes(b"stable")
                        return value
                    return before(paths)
                with patch.object(snapshot, "_snapshot", side_effect=aba), self.assertRaisesRegex(
                        ValueError, "closure changed during snapshot"):
                    snapshot_policy_closure("core-metadata-bootstrap", policy)

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
                    patch.object(snapshot, "_request_paths", return_value={nested}):
                for kind in ("core-metadata", "core-metadata-fresh"):
                    nested.write_text("original")
                    first = snapshot_policy_closure(kind, descriptor)
                    nested.write_text("changed")
                    self.assertNotEqual(first, snapshot_policy_closure(kind, descriptor))
                original.pop("captureRoot")
                original.update(artifactId=1, artifactSha256="sha256:" + "a" * 64)
                first = snapshot_policy_closure("core-metadata-fresh", descriptor)
                nested.write_text("changed again with locator inputs")
                self.assertNotEqual(first, snapshot_policy_closure("core-metadata-fresh", descriptor))
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
                    patch.object(snapshot, "_request_paths", return_value={nested}):
                first = snapshot_policy_closure("android-metadata", descriptor)
                (contract / "input.txt").write_text("changed")
                self.assertNotEqual(first, snapshot_policy_closure("android-metadata", descriptor))


class PolicyPathSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ci.tests.test_sdk_validation_inputs import SdkValidationInputsTest as fixture
        from ci.products.sdk_compatibility import load_sdk_compatibility_request
        fixture.setUpClass()
        cls.addClassCleanup(fixture.doClassCleanups)
        cls.request = fixture.original / "request.json"
        cls.payload = load_sdk_compatibility_request(cls.request)["contract_payload"]
        cls.tooling = fixture.original

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.measurements = []

    def counted(self, operation, kind):
        from ci.products import inventory, sdk_validation_inputs
        opened, digested = [], []
        original_open, original_digest = sdk_validation_inputs._open_regular_file, inventory._regular_file_digest
        def opening(path, *args, **kwargs):
            value = original_open(path, *args, **kwargs)
            if Path(path) == self.payload:
                opened.append(value[1].st_size)
            return value
        def digest(path, **kwargs):
            value = original_digest(path, **kwargs)
            if Path(path) == self.payload:
                digested.append(value[0])
            return value
        with patch.object(sdk_validation_inputs, "_open_regular_file", side_effect=opening), \
                patch.object(inventory, "_regular_file_digest", side_effect=digest):
            result = operation()
        self.measurements.append({"kind": kind, "enumerationHashes": len(opened),
            "finalPayloadHashes": len(digested), "logicalPayloadHashBytes": sum(opened + digested),
            "payloadBytes": self.payload.stat().st_size})
        return result

    def test_core_and_android_paths_are_selected_without_throwaway_payload_hashes(self):
        descriptor = self.work / "policy.json"
        descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": str(self.work), "records": [], "policy": {}}))
        original = {"facadeRequest": str(self.request), "validationReceipt": str(self.request)}
        from ci.products.registry import SDK_FACADE_TARGETS
        arguments = {"validations": {target: original for target in SDK_FACADE_TARGETS}}
        with patch.object(snapshot, "core_arguments", return_value=arguments), \
                patch.object(snapshot, "fresh_metadata_arguments", return_value=arguments), \
                patch.object(snapshot, "facade_request", return_value=({"compatibilityRequest": str(self.request)}, b"")), \
                patch.object(snapshot, "facade_sources", return_value=({}, {}, {})), \
                patch.object(snapshot, "android_arguments", return_value={"binary_contract_evidence": {}, "compatibility_request": self.request}), \
                patch.object(snapshot.sdk_android_validation_phase, "_contract_sources", return_value=({}, {})):
            for kind in ("core-metadata", "core-metadata-fresh", "android-metadata"):
                self.counted(lambda: snapshot_policy_closure(kind, descriptor), kind)
            before = snapshot_policy_closure("android-metadata", descriptor)
            payload = self.payload.read_bytes()
            try:
                self.payload.write_bytes(payload + b"changed")
                self.assertNotEqual(before, snapshot_policy_closure("android-metadata", descriptor))
                self.payload.unlink()
                self.payload.symlink_to(self.request)
                with self.assertRaises(ValueError):
                    snapshot_policy_closure("android-metadata", descriptor)
            finally:
                if self.payload.is_symlink(): self.payload.unlink()
                self.payload.write_bytes(payload)
        self.assertEqual([(0, 1)] * 3, [(row["enumerationHashes"], row["finalPayloadHashes"]) for row in self.measurements])

    def test_fresh_bootstrap_hashes_shared_payload_once_after_path_selection(self):
        from ci import sdk_facade_original_inputs as holder
        from ci.products.registry import SDK_FACADE_TARGETS, SDK_FACADE_CONTRACT_COMPONENTS
        archive = self.work / "native.zip"
        archive.write_bytes(b"synthetic archive identity; no native proof")
        records = {target: {"validationReceipt": str(self.request), "facadeRequest": str(self.request),
            **({"nativeCompilerArchive": str(archive)} if target not in holder._NON_NATIVE_TARGETS else {})}
            for target in SDK_FACADE_TARGETS}
        policy = {"plan": str(self.request), "toolingEvidence": str(self.tooling),
            "toolingPublicKey": str(self.request), "javaExecutable": str(self.request),
            "toolingKeyring": None, "toolingKeysDirectory": None, "toolingTrustDomain": "development",
            "validations": records, "contractDigest": "sha256:" + "a" * 64,
            "componentDigests": {name: "sha256:" + "b" * 64 for name in SDK_FACADE_CONTRACT_COMPONENTS.values()}}
        with patch.object(holder, "_request", return_value=({"compatibilityRequest": str(self.request)}, b"")), \
                patch.object(holder, "_sources", return_value=({}, {}, {})):
            before = self.counted(lambda: holder._fresh_policy_sources(policy), "core-metadata-bootstrap")
            self.assertIn(self.payload, before[0])
            payload = self.payload.read_bytes()
            try:
                self.payload.write_bytes(payload + b"changed")
                self.assertNotEqual(before, holder._fresh_policy_sources(policy))
            finally:
                self.payload.write_bytes(payload)
        self.assertEqual([(0, 1)], [(row["enumerationHashes"], row["finalPayloadHashes"]) for row in self.measurements])


if __name__ == "__main__":
    unittest.main()
