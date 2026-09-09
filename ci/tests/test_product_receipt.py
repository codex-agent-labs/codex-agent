from __future__ import annotations

from pathlib import Path
import os
import tempfile
import threading
import unittest
from unittest import mock

import ci.products.receipt as product_receipt
from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.products.receipt import (
    build_key_payload,
    compute_build_key,
    validate_receipt_inputs,
    write_output_manifest,
    write_phase_receipt,
)


DIGEST_A = sha256_bytes(b"a")
DIGEST_B = sha256_bytes(b"b")
DIGEST_C = sha256_bytes(b"c")
COMMIT = "0123456789abcdef0123456789abcdef01234567"
TREE = "89abcdef0123456789abcdef0123456789abcdef"


class ProductReceiptEmissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stage = self.root / "stage"
        self.receipts = self.root / "receipts"
        self.receipts.mkdir()
        payload = self.stage / "outputs/library/value.bin"
        payload.parent.mkdir(parents=True)
        payload.write_bytes(b"payload")
        write_output_manifest(
            self.stage,
            "runtime",
            "linux-x64",
            "binary",
            "linux-x64",
            "1.2.3",
            {"runtime-library": "outputs/library"},
        )

    @staticmethod
    def inputs() -> dict:
        inventory = [
            {"relativePath": "native/source.kt", "bytes": 1, "sha256": DIGEST_A},
        ]
        return {
            "inventory": inventory,
            "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
            "versionIdentity": "1.2.0",
            "upstreamArtifacts": [],
            "toolchainProfileDigest": DIGEST_B,
            "flagsDigest": DIGEST_C,
            "outputSchemaVersion": 1,
        }

    @staticmethod
    def producer() -> dict:
        return {
            "repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/desktop-runtime-evidence.yml",
            "commit": COMMIT,
            "tree": TREE,
            "event": "pull_request",
            "runId": 7,
            "runAttempt": 1,
            "pullRequest": 31,
        }

    def emit(self, **overrides):
        inputs = overrides.get("inputs", self.inputs())
        values = {
            "stage_root": self.stage,
            "receipt_root": self.receipts,
            "product": "runtime",
            "component": "linux-x64",
            "phase": "binary",
            "target": "linux-x64",
            "product_version": "1.2.3",
            "expected_build_key": compute_build_key(
                product="runtime",
                component="linux-x64",
                phase="binary",
                target="linux-x64",
                inputs=inputs,
            ),
            "inputs": inputs,
            "producer": self.producer(),
            "trust_domain": "development",
        }
        values.update(overrides)
        return write_phase_receipt(**values)

    def assert_failure_removes_stale(self, **overrides) -> None:
        path = self.receipts / "phase-receipt.json"
        path.write_bytes(b'{"stale":true}\n')
        with self.assertRaises(ValueError):
            self.emit(**overrides)
        self.assertFalse(path.exists())

    def test_exact_output_paths_reject_unverified_siblings_without_deleting_payloads(self) -> None:
        expected = ["outputs/library/value.bin"]
        arguments = (self.stage, "runtime", "linux-x64", "binary", "linux-x64", "1.2.3",
                     {"runtime-library": "outputs/library"})
        before = (self.stage / "output-manifest.json").read_bytes()
        write_output_manifest(*arguments, expected_output_paths=expected)
        self.assertEqual(before, (self.stage / "output-manifest.json").read_bytes())
        sibling = self.stage / "outputs/library/unverified.bin"
        sibling.write_bytes(b"preserve me")
        for allowed in (expected, [], expected * 2, ["../escape"], ["/absolute"]):
            with self.subTest(allowed=allowed), self.assertRaises(ValueError):
                write_output_manifest(*arguments, expected_output_paths=allowed)
            self.assertFalse((self.stage / "output-manifest.json").exists())
            self.assertEqual(b"preserve me", sibling.read_bytes())
            self.assertEqual(b"payload", (self.stage / expected[0]).read_bytes())

    def test_exact_file_root_can_share_outputs_with_a_disjoint_directory(self) -> None:
        manifest_file = self.stage / "outputs/aggregate.json"
        manifest_file.write_bytes(b"{}\n")
        arguments = (self.stage, "runtime", "runtime-aggregate", "metadata", "aggregate", "1.2.3")
        roots = {"runtime-aggregate": "outputs/aggregate.json", "maven": "outputs/library"}
        value = write_output_manifest(*arguments, roots)
        self.assertEqual([("runtime-aggregate", "outputs/aggregate.json"),
                          ("maven", "outputs/library/value.bin")],
                         [(record["kind"], record["relativePath"]) for record in value["outputs"]])
        for invalid in ({**roots, "ambiguous": "outputs"}, {**roots, "alias": "outputs/aggregate.json"}):
            with self.assertRaises(ValueError):
                write_output_manifest(*arguments, invalid)
        sibling = self.stage / "outputs/undeclared.json"
        sibling.write_bytes(b"preserve\n")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            write_output_manifest(*arguments, roots)
        self.assertEqual(b"{}\n", manifest_file.read_bytes())
        self.assertEqual(b"preserve\n", sibling.read_bytes())

    def test_emits_canonical_deterministic_receipt_without_changing_stage(self) -> None:
        before = {
            path.relative_to(self.stage).as_posix(): path.read_bytes()
            for path in self.stage.rglob("*")
            if path.is_file()
        }

        first = self.emit()
        path = self.receipts / "phase-receipt.json"
        first_bytes = path.read_bytes()
        second = self.emit()

        self.assertEqual(first, second)
        self.assertEqual(first_bytes, path.read_bytes())
        self.assertEqual(canonical_json_bytes(first), first_bytes)
        self.assertEqual("success", first["result"])
        self.assertEqual("development", first["trustDomain"])
        self.assertEqual(self.inputs(), first["inputs"])
        self.assertEqual(
            before,
            {
                member.relative_to(self.stage).as_posix(): member.read_bytes()
                for member in self.stage.rglob("*")
                if member.is_file()
            },
        )

    def test_rejects_mismatched_exact_identity_and_removes_stale_receipt(self) -> None:
        self.assert_failure_removes_stale(component="linux-arm64")

    def test_local_provenance_is_development_only_and_does_not_change_content_keys(self) -> None:
        local = {**self.producer(), "event": "local", "workflowPath": None,
                 "runId": None, "runAttempt": None, "pullRequest": None}
        first = self.emit(producer=local)
        first_bytes = (self.receipts / "phase-receipt.json").read_bytes()
        second = self.emit(producer={**local, "commit": "c" * 40, "tree": "d" * 40})
        self.assertEqual(first["buildKey"], second["buildKey"])
        self.assertEqual(first["outputs"], second["outputs"])
        self.assertNotEqual(first_bytes, (self.receipts / "phase-receipt.json").read_bytes())
        self.assertEqual(local, first["producer"])
        self.assert_failure_removes_stale(producer=local, trust_domain="release")
        for field in ("workflowPath", "runId", "runAttempt", "pullRequest"):
            with self.subTest(field=field):
                self.assert_failure_removes_stale(producer={**local, field: self.producer()[field]})
        for field in ("repository", "commit", "tree"):
            with self.subTest(field=field):
                self.assert_failure_removes_stale(producer={**local, field: None})
        for event in ("pull_request", "merge_group", "workflow_dispatch", "push"):
            with self.subTest(event=event):
                self.assert_failure_removes_stale(producer={**local, "event": event})

    def test_rejects_invalid_inputs_and_removes_stale_receipt(self) -> None:
        inputs = self.inputs()
        inputs["extra"] = True
        self.assert_failure_removes_stale(inputs=inputs)

    def test_rejects_inventory_digest_mismatch_and_removes_stale_receipt(self) -> None:
        inputs = self.inputs()
        inputs["phaseInputDigest"] = DIGEST_A
        self.assert_failure_removes_stale(inputs=inputs)

    def test_rejects_key_changed_after_planning_and_removes_stale_receipt(self) -> None:
        planned_inputs = self.inputs()
        expected_build_key = compute_build_key(
            product="runtime",
            component="linux-x64",
            phase="binary",
            target="linux-x64",
            inputs=planned_inputs,
        )
        changed_inputs = self.inputs()
        changed_inputs["flagsDigest"] = DIGEST_A
        self.assert_failure_removes_stale(
            inputs=changed_inputs,
            expected_build_key=expected_build_key,
        )

    def test_rejects_changed_output_and_removes_stale_receipt(self) -> None:
        (self.stage / "outputs/library/value.bin").write_bytes(b"changed")
        self.assert_failure_removes_stale()

    def test_rejects_invalid_producer_and_removes_stale_receipt(self) -> None:
        producer = self.producer()
        producer["event"] = "push"
        self.assert_failure_removes_stale(producer=producer)

    def test_rejects_invalid_trust_domain_and_removes_stale_receipt(self) -> None:
        self.assert_failure_removes_stale(trust_domain="untrusted")

    def test_rejects_stale_noncanonical_manifest_and_removes_stale_receipt(self) -> None:
        manifest = self.stage / "output-manifest.json"
        manifest.write_bytes(b"{}\n")
        self.assert_failure_removes_stale()

    def test_rejects_symbolic_stage_output_and_removes_stale_receipt(self) -> None:
        payload = self.stage / "outputs/library/value.bin"
        external = self.root / "external.bin"
        external.write_bytes(payload.read_bytes())
        payload.unlink()
        try:
            payload.symlink_to(external)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symbolic links are unavailable: {error}")
        self.assert_failure_removes_stale()

    def test_runtime_validation_projection_normalizes_only_outputs_digest(self) -> None:
        def inputs(raw_digest: str, semantic_digest: str) -> dict:
            value = self.inputs()
            value["upstreamArtifacts"] = [{
                "product": "runtime",
                "component": "linux-x64",
                "phase": "validation",
                "target": "linux-x64",
                "buildKey": DIGEST_A,
                "outputsDigest": raw_digest,
                "semanticProjection": {
                    "schemaVersion": 1,
                    "kind": "runtime-validation-content",
                    "sha256": semantic_digest,
                },
            }]
            return validate_receipt_inputs(value)

        first = inputs(DIGEST_B, DIGEST_C)
        second = inputs(DIGEST_A, DIGEST_C)
        keys = {
            name: compute_build_key(
                product="runtime", component="linux-x64", phase="metadata",
                target="linux-x64", inputs=value,
            )
            for name, value in (("first", first), ("second", second))
        }
        self.assertEqual(keys["first"], keys["second"])
        normalized = build_key_payload(
            product="runtime", component="linux-x64", phase="metadata",
            target="linux-x64", inputs=first,
        )["upstreamArtifacts"][0]
        self.assertEqual(DIGEST_C, normalized["outputsDigest"])
        self.assertEqual(DIGEST_A, normalized["buildKey"])
        self.assertNotIn("semanticProjection", normalized)
        self.assertEqual(DIGEST_B, first["upstreamArtifacts"][0]["outputsDigest"])
        self.assertIn("semanticProjection", first["upstreamArtifacts"][0])

        changed = inputs(DIGEST_B, DIGEST_A)
        self.assertNotEqual(
            keys["first"],
            compute_build_key(
                product="runtime", component="linux-x64", phase="metadata",
                target="linux-x64", inputs=changed,
            ),
        )

    def test_runtime_validation_projection_schema_and_edge_are_restricted(self) -> None:
        upstream = {
            "product": "runtime",
            "component": "linux-x64",
            "phase": "validation",
            "target": "linux-x64",
            "buildKey": DIGEST_A,
            "outputsDigest": DIGEST_B,
            "semanticProjection": {
                "schemaVersion": 1,
                "kind": "runtime-validation-content",
                "sha256": DIGEST_C,
            },
        }
        for mutation in (
            {**upstream, "semanticProjection": {**upstream["semanticProjection"], "extra": True}},
            {**upstream, "semanticProjection": {**upstream["semanticProjection"], "kind": "wrong"}},
            {**upstream, "semanticProjection": {**upstream["semanticProjection"], "sha256": "bad"}},
            {**upstream, "contractProjection": {}},
        ):
            value = self.inputs()
            value["upstreamArtifacts"] = [mutation]
            with self.assertRaises(ValueError):
                validate_receipt_inputs(value)

        value = self.inputs()
        value["upstreamArtifacts"] = [upstream]
        with self.assertRaisesRegex(ValueError, "unauthorized edge"):
            compute_build_key(
                product="sdk", component="python", phase="metadata",
                target="desktop", inputs=value,
            )

    def test_cleanup_rejects_root_swap_without_touching_external_receipt(self) -> None:
        cleanup_root = self.root / "cleanup"
        cleanup_root.mkdir()
        (cleanup_root / "phase-receipt.json").write_bytes(b"stale")
        moved = self.root / "moved-cleanup"
        external = self.root / "external-cleanup"
        external.mkdir()
        external_receipt = external / "phase-receipt.json"
        external_receipt.write_bytes(b"external")
        original = product_receipt.require_regular_directory

        def swap_after_validation(path: Path, label: str) -> Path:
            result = original(path, label)
            cleanup_root.rename(moved)
            cleanup_root.symlink_to(external, target_is_directory=True)
            return result

        with mock.patch.object(
            product_receipt,
            "require_regular_directory",
            side_effect=swap_after_validation,
        ), self.assertRaisesRegex(ValueError, "changed while opening"):
            product_receipt._remove_phase_receipt(cleanup_root)
        self.assertEqual(b"external", external_receipt.read_bytes())
        self.assertEqual(b"stale", (moved / "phase-receipt.json").read_bytes())

    @unittest.skipUnless(os.name == "nt", "Windows delete-sharing semantics")
    def test_windows_cleanup_handle_blocks_root_replacement_until_unlink(self) -> None:
        cleanup_root = self.root / "windows-cleanup"
        cleanup_root.mkdir()
        receipt = cleanup_root / "phase-receipt.json"
        receipt.write_bytes(b"stale")
        moved = self.root / "windows-moved"
        attempted = threading.Event()
        finished = threading.Event()
        blocked: list[bool] = []
        original_unlink = Path.unlink

        def swap() -> None:
            attempted.set()
            try:
                cleanup_root.rename(moved)
            except OSError:
                blocked.append(True)
            finally:
                finished.set()

        def unlink_while_swap_is_attempted(path: Path, *args, **kwargs) -> None:
            worker = threading.Thread(target=swap)
            worker.start()
            self.assertTrue(attempted.wait(5))
            self.assertTrue(finished.wait(5))
            worker.join()
            original_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "unlink", side_effect=unlink_while_swap_is_attempted):
            product_receipt._remove_phase_receipt(cleanup_root)
        self.assertEqual([True], blocked)
        self.assertTrue(cleanup_root.is_dir())
        self.assertFalse(receipt.exists())


if __name__ == "__main__":
    unittest.main()
