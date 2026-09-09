"""iOS SDK property translation fixtures, not Apple execution evidence."""

from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sdk_ios_phase import TASK, properties  # noqa: E402


class SdkIosPhaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-phase-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.contract = self.root / "contract"
        self.distribution = self.root / "verified-distribution"
        self.native = self.root / "native-evidence"
        for directory in (self.contract, self.distribution, self.native):
            directory.mkdir()
        self.request = self.root / "compatibility-request.json"
        self.request.write_bytes(b"caller-authenticated request fixture\n")
        self.compatibility = self.root / "sdk-compatibility.json"
        self.compatibility.write_bytes(b"caller-authenticated compatibility fixture\n")
        self.proof = self.root / "original-apple-proof.json"
        self.proof.write_bytes(b"caller-authenticated original proof fixture\n")
        self.calls = []
        self.record = {
            "stage": self.contract,
            "receiptPath": self.root / "contract-receipt.json",
            "receipt": {
                "product": "contract", "component": "contract",
                "phase": "binary", "target": "common", "productVersion": "0.2.0",
            },
        }

    @staticmethod
    def plan(**changes):
        return {
            "product": "sdk", "component": "sdk-ios",
            "phase": "package", "target": "ios", **changes,
        }

    def predecessor(self, *identity):
        self.calls.append(identity)
        return self.record

    def translate(self, **changes):
        return properties(
            self.plan(), predecessor=self.predecessor,
            verified_distribution=changes.get("verified_distribution", self.distribution),
            native_evidence=changes.get("native_evidence", self.native),
            compatibility_request=changes.get("compatibility_request", self.request),
            expected_sdk_compatibility=changes.get("expected_sdk_compatibility", self.compatibility),
            expected_distribution_proof=changes.get("expected_distribution_proof", self.proof),
        )

    def test_exact_original_inputs_route_to_the_existing_transported_verifier(self):
        self.assertEqual(
            ":codex-agent-runtime-ios:verifyTransportedCodexAgentIosSdkPackageClosure", TASK,
        )
        self.assertEqual({
            "codexAgent.contractBinaryStage": str(self.contract),
            "codexAgent.contractVersion": "0.2.0",
            "codexAgent.iosVerifiedDistributionDirectory": str(self.distribution),
            "codexAgent.iosNativeEvidenceDirectory": str(self.native),
            "codexAgent.sdkCompatibilityRequest": str(self.request),
            "codexAgent.iosExpectedSdkCompatibility": str(self.compatibility),
            "codexAgent.iosExpectedDistributionProof": str(self.proof),
        }, self.translate())
        self.assertEqual([("contract", "contract", "binary", "common")], self.calls)

    def test_unsupported_identity_rejects_before_inputs_or_callback(self):
        for changes in (
            {"product": "runtime"}, {"component": "sdk-core"},
            {"phase": "binary"}, {"phase": "validation"}, {"target": "common"},
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "Unsupported"):
                properties(
                    self.plan(**changes), predecessor=self.predecessor,
                    verified_distribution=Path("relative"), native_evidence=Path("relative"),
                    compatibility_request=Path("relative"),
                    expected_sdk_compatibility=Path("relative"), expected_distribution_proof=Path("relative"),
                )
        self.assertEqual([], self.calls)

    def test_crosspaired_or_invalid_contract_receipt_fails_closed(self):
        original = self.record
        for field, value in (
            ("product", "sdk"), ("component", "sdk-core"), ("phase", "metadata"),
            ("target", "ios"), ("productVersion", "not-semver"),
        ):
            self.record = {
                **original,
                "receipt": {**original["receipt"], field: value},
            }
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.translate()
        self.record = original

    def test_missing_relative_symbolic_or_wrong_input_types_are_rejected(self):
        empty = self.root / "empty-request"
        empty.write_bytes(b"")
        request_link = self.root / "request-link"
        request_link.symlink_to(self.request)
        directory_link = self.root / "distribution-link"
        directory_link.symlink_to(self.distribution, target_is_directory=True)
        cases = (
            {"verified_distribution": Path("relative")},
            {"verified_distribution": self.root / "missing"},
            {"verified_distribution": self.request},
            {"verified_distribution": directory_link},
            {"native_evidence": Path("relative")},
            {"native_evidence": self.root / "missing"},
            {"compatibility_request": Path("relative")},
            {"compatibility_request": self.root / "missing"},
            {"compatibility_request": self.distribution},
            {"compatibility_request": request_link},
            {"compatibility_request": empty},
            {"expected_sdk_compatibility": empty},
            {"expected_sdk_compatibility": request_link},
            {"expected_distribution_proof": self.root / "missing"},
            {"expected_distribution_proof": request_link},
            {"expected_distribution_proof": Path("relative")},
        )
        for changes in cases:
            self.calls.clear()
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.translate(**changes)
            self.assertEqual([], self.calls)

        contract_link = self.root / "contract-link"
        contract_link.symlink_to(self.contract, target_is_directory=True)
        self.record = {**self.record, "stage": contract_link}
        with self.assertRaises(ValueError):
            self.translate()


if __name__ == "__main__":
    unittest.main()
