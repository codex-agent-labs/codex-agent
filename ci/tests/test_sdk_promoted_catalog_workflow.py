"""Static trust boundary for the uncalled promoted SDK catalog child."""

from pathlib import Path
import unittest

from ci.sdk_catalog_promotion_caller import _require_promoted_caller


_WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/sdk-promoted-catalog.yml"


class SdkPromotedCatalogWorkflowTest(unittest.TestCase):
    def test_two_jobs_keep_observation_and_release_key_separate(self):
        source = _WORKFLOW.read_text()
        self.assertIn("  workflow_call:\n", source)
        self.assertNotIn("  push:\n", source)
        self.assertNotIn("  workflow_dispatch:\n", source)
        capture, sign = source.split("  sign:\n", 1)
        self.assertIn("environment: product-catalog-observation", capture)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", capture)
        self.assertNotIn("secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", capture)
        self.assertIn("environment: product-attestation", sign)
        self.assertIn("needs: capture", sign)
        self.assertNotIn("GITHUB_TOKEN:", sign)
        self.assertIn("RELEASE_PRIVATE_KEY: ${{ secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY }}", sign)
        self.assertLess(sign.index("unset RELEASE_PRIVATE_KEY CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"),
                        sign.index("python3 -B -m ci.sdk_catalog_promotion_caller sign"))

    def test_approved_bytes_gate_both_jobs_before_signing(self):
        source = _WORKFLOW.read_text()
        capture, sign = source.split("  sign:\n", 1)
        self.assertLess(capture.index("CODEX_AGENT_SDK_PROMOTION_CONTROL_APPROVED_SHA256"),
                        capture.index("uses: actions/checkout@"))
        self.assertIn("catalogCaptureInventorySha256", capture)
        self.assertIn("indexCarrierInventorySha256", capture)
        self.assertIn("SDK promotion control has wrong schema", capture)
        self.assertLess(sign.index("CODEX_AGENT_SDK_PROMOTION_CONTROL_APPROVED_SHA256"),
                        sign.index("uses: actions/checkout@"))
        self.assertLess(sign.index("SDK capture control differs from independent signing approval"),
                        sign.index("python3 -B -m ci.sdk_catalog_promotion_caller sign"))
        self.assertIn("--index-carrier-capture", sign)
        self.assertIn("--expected-index-carrier-inventory-sha256", sign)
        self.assertNotIn("gradlew", source)

    def test_signer_rejects_another_protected_push_caller(self):
        commit = "a" * 40
        environment = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main",
            "GITHUB_REF_PROTECTED": "true", "GITHUB_SHA": commit,
            "GITHUB_WORKFLOW_REF": (
                "codex-agent-labs/codex-agent/.github/workflows/promote.yml"
                "@refs/heads/main")}
        _require_promoted_caller(environment, commit)
        with self.assertRaisesRegex(ValueError, "fixed protected-main promotion caller"):
            _require_promoted_caller({**environment, "GITHUB_WORKFLOW_REF": (
                "codex-agent-labs/codex-agent/.github/workflows/ci.yml@refs/heads/main")},
                commit)


if __name__ == "__main__":
    unittest.main()
