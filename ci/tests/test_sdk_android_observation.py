"""Protected submission byte binding; receipt semantics are independently tested."""

import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from ci.products import sdk_android_observation as observation
from ci.products.inventory import canonical_json_bytes, regular_file_inventory
from ci.tests import test_sdk_apple_package_source as fixtures


class AndroidObservationTest(unittest.TestCase):
    def setUp(self):
        self.f = self.enterContext(fixtures.RepositoryFixture())
        commit = self.f.commit()
        self.lane = self.f.root / "lane"
        self.plan = self.f.root / "plan.json"
        self.plan.write_bytes(b"original plan\n")
        for name, relative in observation.SUBMISSION_FILES.items():
            path = self.lane / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((name + " original\n").encode())
        self.expected_receipt = {"validationCommit": "a" * 40, "validationTree": "b" * 40}
        self.checked = self.enterContext(patch.object(observation, "validate_receipt", return_value=self.expected_receipt))
        self.arguments = dict(repository=self.f.repository, lane=self.lane, plan=self.plan,
                              observation=self.f.output, candidate_commit="a" * 40, candidate_tree="b" * 40,
                              trusted_source_commit=commit,
                              trusted_source_tree=self.f.git("rev-parse", "HEAD^{tree}"))

    def call(self, create=False, **changes):
        observation.bind_submission(**{**self.arguments, **changes}, create=create)

    def test_create_and_verify_preserve_exact_receipt_and_canonical_binding(self):
        before = regular_file_inventory(self.lane)
        self.call(create=True)
        self.call()
        raw = (self.f.output / "input-binding.json").read_bytes()
        value = json.loads(raw)
        self.assertEqual(raw, canonical_json_bytes(value))
        self.assertEqual(sorted(observation.SUBMISSION_FILES), [row["relativePath"] for row in value["files"]])
        self.assertTrue(all(row["sha256"].startswith("sha256:") for row in value["files"]))
        self.assertEqual((self.lane / "lane-receipt.json").read_bytes(), (self.f.output / "lane-receipt.json").read_bytes())
        self.assertEqual(before, regular_file_inventory(self.lane))
        self.checked.assert_called_with(self.lane / "lane-receipt.json", self.plan, self.lane, "android")
        with self.assertRaises(ValueError):
            self.call(create=True)
        self.assertEqual(raw, (self.f.output / "input-binding.json").read_bytes())

    def test_every_submitted_file_and_policy_identity_is_bound(self):
        self.call(create=True)
        for relative in observation.SUBMISSION_FILES.values():
            path = self.lane / relative
            original = path.read_bytes()
            path.write_bytes(original + b"mutated")
            with self.subTest(path=relative), self.assertRaises(ValueError):
                self.call()
            path.write_bytes(original)
        for field in ("candidate_commit", "candidate_tree", "trusted_source_commit", "trusted_source_tree"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.call(**{field: "f" * 40})

    def test_dirty_source_bad_receipt_and_unsafe_inputs_reject(self):
        self.f.write("LICENSE", "dirty\n")
        with self.assertRaises(subprocess.CalledProcessError):
            self.call(create=True)
        self.assertFalse(self.f.output.exists())
        self.f.write("LICENSE", "license\n")
        self.checked.side_effect = ValueError("real lane check rejected")
        with self.assertRaisesRegex(ValueError, "real lane"):
            self.call(create=True)
        self.checked.side_effect = None
        path = self.lane / observation.SUBMISSION_FILES["application.apk"]
        saved = self.f.root / "saved.apk"
        path.rename(saved)
        path.symlink_to(saved)
        with self.assertRaises(ValueError):
            self.call(create=True)
        self.assertFalse(self.f.output.exists())

    def test_observation_and_late_input_mutations_reject(self):
        self.call(create=True)
        binding = self.f.output / "input-binding.json"
        binding.write_bytes(binding.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.call()
        self.arguments["observation"] = self.f.root / "second"
        original = observation.publish_regular_tree
        def mutate(*args, **kwargs):
            result = original(*args, **kwargs)
            self.plan.write_bytes(b"late plan change\n")
            return result
        with patch.object(observation, "publish_regular_tree", side_effect=mutate), self.assertRaises(ValueError):
            self.call(create=True)

    def test_workflow_pins_main_once_and_checks_before_and_after_submission(self):
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/android-runtime-evidence.yml").read_text()
        self.assertEqual(1, workflow.count("/git/ref/heads/main"))
        self.assertNotIn("ref: main", workflow)
        self.assertIn("ref: ${{ steps.trusted-source.outputs.commit }}", workflow)
        self.assertIn("ref: ${{ needs.firebase-arm64-runtime.outputs.trusted_source_commit }}", workflow)
        self.assertLess(workflow.index("bind_inputs create"), workflow.index("gcloud firebase test android run"))
        self.assertLess(workflow.index("gcloud firebase test android run"), workflow.index("bind_inputs verify"))
        self.assertLess(workflow.index("Require the exact protected submission"), workflow.index("Record evidence against"))
        self.assertIn("--num-flaky-test-attempts=0 --timeout=15m", workflow)


if __name__ == "__main__":
    unittest.main()
