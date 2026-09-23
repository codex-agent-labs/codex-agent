"""Fresh Android metadata policy must bind every successful worker output."""

import tempfile
import unittest
from pathlib import Path

from ci.sdk_android_original_control import compose, main
from ci.products.inventory import load_canonical_json_bytes, write_canonical_json


class AndroidOriginalControlTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="android-original-control-")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name).resolve()
        self.repository = root / "workspace"
        self.repository.mkdir()
        source = root / "source"
        source.write_bytes(b"independent source")
        directory = root / "tree"
        directory.mkdir()
        (directory / "evidence").write_bytes(b"original")
        self.base = {
            "packageStage": str(directory), "packageReceipt": str(source),
            "binaryStage": str(directory), "binaryReceipt": str(source),
            "compatibilityRequest": str(source), "binaryContractEvidence": str(source),
            "trustedSourceCommit": "a" * 40, "trustedSourceTree": "b" * 40,
            "toolingEvidence": str(directory), "toolingPublicKey": str(source),
            "javaExecutable": str(source), "apkanalyzerExecutable": str(source),
            "toolingTrustDomain": "development", "toolingKeyring": None,
            "toolingKeysDirectory": None, "trustedAndroidWorkflowSha": "c" * 40,
        }
        self.outputs = {
            "validationReceiptSha256": "sha256:" + "d" * 64,
            "validationArtifactId": 17,
            "validationArtifactSha256": "sha256:" + "e" * 64,
            "validationRunId": 29, "validationRunAttempt": 2,
        }

    def compose(self, *, base=None, outputs=None):
        return compose(self.base if base is None else base,
                       self.outputs if outputs is None else outputs,
                       expected_run_id=29, expected_run_attempt=2,
                       repository_root=self.repository)

    def test_exact_successful_outputs_and_independent_source_are_preserved(self):
        policy = self.compose()
        self.assertEqual(self.outputs["validationReceiptSha256"],
                         policy["validationReceiptSha256"])
        self.assertEqual(self.outputs["validationArtifactSha256"],
                         policy["validationArtifactSha256"])
        self.assertEqual((29, 2), (policy["expectedOriginalRunId"],
                                    policy["expectedOriginalRunAttempt"]))
        self.assertEqual(22, len(policy))

    def test_missing_or_cross_paired_worker_outputs_fail_closed(self):
        for field in self.outputs:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.compose(outputs={key: value for key, value in self.outputs.items()
                                      if key != field})
        with self.assertRaisesRegex(ValueError, "selected campaign attempt"):
            self.compose(outputs={**self.outputs, "validationRunAttempt": 1})
        with self.assertRaises(ValueError):
            self.compose(outputs={**self.outputs,
                                  "validationReceiptSha256": "sha256:" + "z" * 64})

    def test_source_not_reconstructed_from_worker_or_retained_state(self):
        with self.assertRaises(ValueError):
            self.compose(base={**self.base, "packageReceipt": "relative/receipt.json"})
        with self.assertRaises(ValueError):
            self.compose(base={**self.base, "toolingTrustDomain": "release"})
        with self.assertRaises(ValueError):
            self.compose(base={**self.base, "trustedSourceTree": "unselected"})
        inside = self.repository / "retained-receipt.json"
        inside.write_bytes(b"untrusted retained state")
        with self.assertRaisesRegex(ValueError, "source checkout"):
            self.compose(base={**self.base, "packageReceipt": str(inside)})

    def test_cli_writes_one_external_canonical_policy(self):
        root = self.repository.parent
        base = root / "base-policy.json"
        destination = root / "original-policy.json"
        write_canonical_json(base, self.base)
        arguments = ["--base-policy", str(base), "--destination", str(destination),
                     "--repository-root", str(self.repository)]
        for flag, value in (
                ("validation-receipt-sha256", self.outputs["validationReceiptSha256"]),
                ("validation-artifact-id", self.outputs["validationArtifactId"]),
                ("validation-artifact-sha256", self.outputs["validationArtifactSha256"]),
                ("validation-run-id", self.outputs["validationRunId"]),
                ("validation-run-attempt", self.outputs["validationRunAttempt"]),
                ("expected-run-id", 29), ("expected-run-attempt", 2)):
            arguments.extend(("--" + flag, str(value)))
        self.assertEqual(0, main(arguments))
        self.assertEqual(self.compose(), load_canonical_json_bytes(destination.read_bytes()))
        with self.assertRaises(SystemExit):
            main(arguments)  # immutable destination; no overwrite on retry


if __name__ == "__main__":
    unittest.main()
