"""Retained Android validation election with real immutable object restore."""

from types import SimpleNamespace
from contextlib import redirect_stderr
from io import StringIO
import os
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_android_validation_handoff as handoff
from products.plan import _upstream_record
from products.restore import verify_phase_shard
from ci.tests import test_sdk_facade_capture as fixtures


class AndroidValidationHandoffTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.AndroidValidationCaptureTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        self.discovery, self.state = self.root / "discovery", self.root / "state"
        self.discovery.mkdir(); self.state.mkdir()
        (self.discovery / "control.json").write_bytes(b"original\n")
        (self.state / "control.json").write_bytes(b"original\n")
        shard = verify_phase_shard(self.f.receipt_path.parent, handoff._VALIDATION)
        self.source = self.f.receipt_path.parent / shard["objectPath"]
        self.metadata_key = "sha256:" + "b" * 64
        self.record = {"state": "reused", "buildKey": shard["buildKey"],
            "receiptSha256": shard["receiptSha256"], "objectSha256": shard["objectSha256"]}
        self.verified = SimpleNamespace(
            plan={"validationCommit": "a" * 40, "validationTree": "b" * 40},
            prior_ready_plans={handoff._METADATA: {
                "buildKey": self.metadata_key,
                "inputs": {"upstreamArtifacts": [_upstream_record(self.f.receipt)]}}},
            prior_by_instance={handoff._VALIDATION: self.record},
            prior_carrier_phases={handoff._VALIDATION: self.record.copy()},
            sources={handoff._VALIDATION: self.source})
        self.arguments = dict(
            plan=self.f.plan_path, discovery=self.discovery, state=self.state,
            expected_metadata_build_key=self.metadata_key,
            trusted_workflow_sha="c" * 40, repository_root=self.root,
            environ={}, token="synthetic-token")
        self.enterContext(patch.object(handoff.product_reuse, "_verified_product_state",
                               return_value=self.verified))
        self.enterContext(patch.object(handoff.product_reuse, "_git_value",
                               side_effect=lambda root, command, revision:
                               "b" * 40 if revision.endswith("{tree}") else "a" * 40))
        self.locator = self.enterContext(patch.object(
            handoff, "locate_sdk_android_validation_upload", return_value={
                "artifact_id": 701, "artifact_sha256": "sha256:" + "d" * 64}))

    def call(self, **changes):
        return handoff.validation_handoff(**{**self.arguments, **changes})

    def test_elected_object_selects_official_locator_and_original_producer(self):
        self.assertEqual({
            "validation_receipt_sha256": self.record["receiptSha256"],
            "validation_artifact_id": 701,
            "validation_artifact_sha256": "sha256:" + "d" * 64,
            "validation_run_id": self.f.producer["runId"],
            "validation_run_attempt": self.f.producer["runAttempt"],
            "validation_original_mode": "retained",
        }, self.call())
        args, kwargs = self.locator.call_args
        self.assertEqual(self.f.plan_path, args[0])
        self.assertEqual(self.record["receiptSha256"], kwargs["expected_receipt_sha256"])

    def test_wrong_election_missing_original_and_object_tamper_fail_before_lookup(self):
        with self.assertRaisesRegex(ValueError, "elected retained"):
            self.call(expected_metadata_build_key="sha256:" + "0" * 64)
        self.verified.sources.clear()
        with self.assertRaisesRegex(ValueError, "elected retained"):
            self.call()
        self.verified.sources[handoff._VALIDATION] = self.source
        original = self.source.read_bytes()
        tampered = self.root / "tampered-object.zip"
        tampered.write_bytes(original + b"tampered")
        self.verified.sources[handoff._VALIDATION] = tampered
        with self.assertRaises(ValueError):
            self.call()
        self.locator.assert_not_called()

    def test_late_state_mutation_rejects_official_result(self):
        def mutate(*args, **kwargs):
            (self.state / "late.bin").write_bytes(b"changed")
            return {"artifact_id": 701, "artifact_sha256": "sha256:" + "d" * 64}
        self.locator.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.call()

    def test_fresh_coordinates_must_match_elected_original(self):
        original = self.call()
        coordinates = {name: original[name] for name in handoff._COORDINATES}
        self.assertEqual({**original, "validation_original_mode": "fresh"},
                         self.call(fresh_validation=coordinates))
        for name in coordinates:
            changed = coordinates.copy()
            changed[name] = (changed[name] + 1 if isinstance(changed[name], int)
                             else "sha256:" + "0" * 64)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "differ"):
                self.call(fresh_validation=changed)
        with self.assertRaisesRegex(ValueError, "fields are invalid"):
            self.call(fresh_validation={"validation_artifact_id": 701})

    def test_cli_writes_github_output_and_rejects_partial_fresh_coordinates(self):
        output = self.enterContext(tempfile.TemporaryDirectory(prefix="android-handoff-output-"))
        output = handoff.Path(output).resolve() / "github-output"
        output.touch()
        expected = self.call()
        argv = ["--plan", str(self.f.plan_path), "--discovery-root", str(self.discovery),
            "--state-root", str(self.state), "--repository-root", str(self.root),
            "--expected-metadata-build-key", self.metadata_key,
            "--trusted-workflow-sha", "c" * 40, "--github-output", str(output)]
        with patch.dict(os.environ, {"GITHUB_TOKEN": "synthetic-token"}):
            self.assertEqual(0, handoff.main(argv))
            self.assertEqual(
                {name.replace("_", "-") + "=" + str(value) for name, value in expected.items()},
                set(output.read_text().splitlines()))
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                handoff.main(argv + ["--expected-validation-artifact-id", "701"])
            self.assertEqual(6, len(output.read_text().splitlines()))


if __name__ == "__main__":
    unittest.main()
