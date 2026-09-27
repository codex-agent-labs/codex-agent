"""The later SDK record signs only independently approved, replayed bytes."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/sdk-phase10-later-record.yml"


class SdkPhase10RecordWorkflowTest(unittest.TestCase):
    def test_protected_replay_precedes_token_free_signing(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("environment: product-attestation", source)
        self.assertIn("CODEX_AGENT_SDK_PHASE10_CONTROL_APPROVED_SHA256", source)
        self.assertIn("CODEX_AGENT_SDK_INDEX_APPROVED_SHA256", source)
        self.assertIn("sdk_phase10_protected_inputs.py stage", source)
        self.assertIn("sdk_phase10_original_plan.py", source)
        self.assertIn("sdk_campaign_release_issuer.py prepare", source)
        self.assertIn("sdk_campaign_release_issuer.py sign", source)
        self.assertIn("--repository-root \"$PWD/original-source\"", source)
        self.assertLess(source.index("sdk_phase10_protected_inputs.py stage"),
                        source.index("sdk_phase10_original_plan.py"))
        self.assertLess(source.index("sdk_phase10_original_plan.py"),
                        source.index("sdk_campaign_release_issuer.py prepare"))
        self.assertLess(source.index("sdk_campaign_release_issuer.py prepare"),
                        source.index("sdk_campaign_release_issuer.py sign"))
        signer = source.split("      - name: Sign only the preapproved index", 1)[1].split(
            "      - name: Upload exact signed pair", 1)[0]
        self.assertNotIn("GITHUB_TOKEN:", signer)
        self.assertNotIn("GH_TOKEN:", signer)
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", signer)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", source.split(
            "      - name: Sign only the preapproved index", 1)[0])

    def test_upload_is_signed_pair_only(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        upload = source.split("      - name: Upload exact signed pair", 1)[1]
        self.assertIn("path: ${{ runner.temp }}/sdk-signed-index", upload)
        self.assertIn("overwrite: false", upload)
        self.assertNotIn("gradlew", source)
        self.assertNotIn("cargo build", source)


if __name__ == "__main__":
    unittest.main()
