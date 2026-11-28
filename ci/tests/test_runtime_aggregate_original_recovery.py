"""Earlier signed aggregate carrier lookup for completed-frozen ordinary preparation.

GitHub, capture and signature staging are explicit mocks. Their own gates are
covered by their own tests; this pins the selection binding and call shapes.
"""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # Top-level ci modules, as the CLI runs them.
from ci import runtime_signing_preparation as preparation  # noqa: E402
from products.inventory import canonical_json_bytes, sha256_bytes  # noqa: E402

KEY = "sha256:" + "1" * 64
PIN = "2" * 40
ORIGINAL_WORKFLOW = "d2243aac89368df2776b6617fd5a623bd6754cb2"


class OriginalAggregateRecoveryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aggregate-original-recovery-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.selected = self.root / "selected"
        self.producer = {"repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
            "event": "pull_request", "commit": "a" * 40, "tree": "b" * 40,
            "runId": 12, "runAttempt": 2, "pullRequest": 31}
        self.original = {**self.producer, "commit": "c" * 40, "tree": "e" * 40, "runId": 10, "runAttempt": 1}
        self.receipt = {"product": "runtime", "component": "runtime-aggregate", "phase": "metadata",
                        "target": "aggregate", "buildKey": KEY, "producer": self.original}
        self.uploads = [{"id": 77, "digest": "sha256:" + "f" * 64, "size_in_bytes": 1000,
                         "name": f"codex-agent-runtime-aggregate-release-handoff-{'e' * 40}-attempt-1"},
                        {"id": 78, "digest": "sha256:" + "0" * 64, "name": "codex-agent-unrelated"}]
        self.workflow = ORIGINAL_WORKFLOW
        self.calls = []
        for name, side_effect in (("api_json", self.observe_run), ("paginated_items", self.list_uploads),
                                  ("capture_runtime_aggregate_release_upload", self.capture),
                                  ("_runtime_prior_workflow_sha", lambda run, current: self.workflow)):
            mocked = patch(f"product_reuse.{name}", side_effect=side_effect)
            setattr(self, name, mocked.start())
            self.addCleanup(mocked.stop)
        mocked = patch("products.runtime_aggregate_inputs.stage_runtime_aggregate_release_evidence",
                       side_effect=self.stage)
        self.stage_mock = mocked.start()
        self.addCleanup(mocked.stop)
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()
        self.headroom = []
        mocked = patch("runtime_reference_transport.require_volume_headroom",
                       side_effect=lambda root, required, *, stage: self.headroom.append((Path(root), required, stage)))
        mocked.start()
        self.addCleanup(mocked.stop)

    def write_receipt(self, receipt=None):
        raw = canonical_json_bytes(self.receipt if receipt is None else receipt)
        path = self.selected / "predecessors/runtime-runtime-aggregate-metadata-aggregate/phase-receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return {"metadata": {"buildKey": KEY, "receiptSha256": sha256_bytes(raw)}, "producer": self.producer,
                "aggregateReceipt": path.relative_to(self.selected).as_posix()}

    def observe_run(self, url, token):
        self.calls.append(("run", url))
        return {"id": self.original["runId"]}

    def list_uploads(self, url, key, token):
        self.calls.append(("uploads", url))
        return self.uploads

    def capture(self, plan_path, destination, **kwargs):
        self.nested_temporary = Path(tempfile.gettempdir())
        self.calls.append(("capture", destination, kwargs))
        (destination / "original").mkdir(parents=True)

    def stage(self, records, source_root, destination, **kwargs):
        self.calls.append(("stage", records, source_root, destination, kwargs))
        return [{"receiptSha256": records[0]["receiptSha256"], "handoffRoot": "handoffs/original"}]

    def recover(self, selection, **semantic):
        return preparation.recover_original_aggregate_release(self.root / "plan.json", self.selected, selection,
            self.root / "retained-original", keyring=self.root / "keyring.json", keys_directory=self.root / "keys",
            repository_root=self.root / "candidate", environment={"GITHUB_EVENT_NAME": "pull_request",
                preparation.SCRATCH_ENVIRONMENT: str(self.scratch)},
            trusted_workflow_sha=PIN, token="synthetic-token", **semantic)

    def test_completed_capability_reaches_the_capture_gate_with_the_exact_selected_receipt(self):
        """T4: the capture gate, not this lookup, decides an owner-pinned PR-31 producer."""
        capability = object()  # Composition seam; the capture gate rejects forged authority.
        self.producer = {**self.producer, "pullRequest": 37, "runId": 46, "runAttempt": 1}
        selection = self.write_receipt()
        self.recover(selection, completed_frozen=capability)
        capture = next(call for call in self.calls if call[0] == "capture")
        self.assertIs(capability, capture[2]["completed_frozen"])
        self.assertEqual(self.receipt, capture[2]["original_receipt"])
        self.assertEqual(self.original, capture[2]["original_producer"])
        self.assertEqual(selection["metadata"]["receiptSha256"],
                         sha256_bytes(canonical_json_bytes(capture[2]["original_receipt"])))

    def test_earlier_original_upload_is_captured_and_signature_staged(self):
        selection = self.write_receipt()
        result = self.recover(selection)
        self.assertEqual(self.root / "retained-original/handoffs/original", result)
        capture = next(call for call in self.calls if call[0] == "capture")
        self.assertEqual({"artifact_id": 77, "artifact_sha256": "sha256:" + "f" * 64,
            "trusted_workflow_sha": ORIGINAL_WORKFLOW, "expected_build_key": KEY,
            "expected_metadata_receipt_sha256": selection["metadata"]["receiptSha256"],
            "original_producer": self.original, "repository_root": self.root / "candidate",
            "environ": {"GITHUB_EVENT_NAME": "pull_request", preparation.SCRATCH_ENVIRONMENT: str(self.scratch)},
            "token": "synthetic-token"}, capture[2])
        self.assertNotIn(self.root / "candidate", capture[1].parents)
        stage = next(call for call in self.calls if call[0] == "stage")
        self.assertEqual([{"receiptSha256": selection["metadata"]["receiptSha256"], "handoffRoot": "original"}], stage[1])
        self.assertEqual(capture[1], stage[2])
        self.assertEqual(self.root / "retained-original", stage[3])
        self.assertEqual({"keyring": self.root / "keyring.json", "keys_directory": self.root / "keys"}, stage[4])
        self.assertIn(("run", "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/10/attempts/1"),
                      self.calls)

    def test_capture_and_nested_temporaries_use_the_scratch_after_fail_early_headroom(self):
        free = {self.scratch.resolve(): 10 ** 15}
        with patch("shutil.disk_usage", side_effect=lambda path: type("U", (), {
                "free": free.get(Path(path).resolve(), 1)})()):
            self.recover(self.write_receipt())
        capture = next(call for call in self.calls if call[0] == "capture")
        self.assertIn(self.scratch.resolve(), capture[1].parents)
        self.assertIn(self.scratch.resolve(), self.nested_temporary.parents)
        self.assertNotEqual(self.nested_temporary, Path(tempfile.gettempdir()))  # Restored afterwards.
        gib = 1024 ** 3
        self.assertEqual([(self.scratch.resolve(), 6 * 1000 + 2 * gib, "runtime-aggregate-release-recovery-scratch"),
                          (self.root, 1000 + 2 * gib, "runtime-aggregate-release-recovery-output")], self.headroom)

    def test_insufficient_headroom_fails_before_any_download(self):
        with patch("runtime_reference_transport.require_volume_headroom",
                   side_effect=ValueError("Insufficient free space for runtime-aggregate-release-recovery-scratch")):
            with self.assertRaisesRegex(ValueError, "Insufficient free space"):
                self.recover(self.write_receipt())
        self.assertFalse(any(call[0] in ("capture", "stage") for call in self.calls))

    def test_upload_without_transport_size_rejects_before_download(self):
        del self.uploads[0]["size_in_bytes"]
        with self.assertRaisesRegex(ValueError, "transport size"):
            self.recover(self.write_receipt())
        self.assertFalse(any(call[0] in ("capture", "stage") for call in self.calls))

    def test_scratch_environment_must_name_an_existing_absolute_directory(self):
        for value in ("relative/scratch", str(self.root / "missing")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                preparation.preparation_scratch({preparation.SCRATCH_ENVIRONMENT: value})
        link = self.root / "scratch-link"
        link.symlink_to(self.scratch, target_is_directory=True)
        with self.assertRaises(ValueError):
            preparation.preparation_scratch({preparation.SCRATCH_ENVIRONMENT: str(link)})
        self.assertEqual(Path(tempfile.gettempdir()), preparation.preparation_scratch({}))

    def test_current_aggregate_needs_fresh_native_handoffs_without_lookup(self):
        self.receipt["producer"] = self.producer
        self.assertIsNone(self.recover(self.write_receipt()))
        self.assertEqual([], self.calls)

    def test_missing_upload_keeps_the_existing_fail_closed_route(self):
        self.uploads = self.uploads[1:]
        self.assertIsNone(self.recover(self.write_receipt()))
        self.assertFalse(any(call[0] in ("capture", "stage") for call in self.calls))

    def test_unreviewed_workflow_or_ambiguous_upload_rejects(self):
        self.workflow = None
        with self.assertRaisesRegex(ValueError, "reviewed original workflow"):
            self.recover(self.write_receipt())
        self.workflow = ORIGINAL_WORKFLOW
        self.uploads = [self.uploads[0], {**self.uploads[0], "id": 79}]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.recover(self.write_receipt())
        self.assertFalse(any(call[0] in ("capture", "stage") for call in self.calls))

    def test_selection_receipt_mismatches_reject_before_any_lookup(self):
        selection = self.write_receipt()
        for change in (
            lambda value: value["metadata"].update(receiptSha256="sha256:" + "9" * 64),
            lambda value: value["metadata"].update(buildKey="sha256:" + "8" * 64),
            lambda value: value.update(aggregateReceipt="../escape.json"),
        ):
            changed = {**selection, "metadata": dict(selection["metadata"])}
            change(changed)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.recover(changed)
        for field, value in (("component", "linux-x64"), ("buildKey", "sha256:" + "8" * 64)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.recover(self.write_receipt({**self.receipt, field: value}))
        self.assertEqual([], self.calls)


if __name__ == "__main__":
    unittest.main()
