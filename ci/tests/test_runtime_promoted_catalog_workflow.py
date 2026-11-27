"""Source-only guard for the disabled, protected Runtime catalog caller."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CHILD = ROOT / ".github/workflows/runtime-promoted-catalog.yml"
PARENT = CHILD.with_name("promote.yml")


class RuntimePromotedCatalogWorkflowTest(unittest.TestCase):
    def test_parent_is_explicitly_armed_only_on_protected_main(self):
        parent = PARENT.read_text()
        job = parent.split("  runtime-promoted-catalog:\n", 1)[1]
        self.assertIn("github.ref == 'refs/heads/main' && github.ref_protected", job)
        self.assertIn("vars.CI_MERGE_QUEUE_ENABLED == 'true'", job)
        self.assertIn("vars.CODEX_AGENT_RUNTIME_PROMOTION_ENABLED == 'true'", job)
        self.assertIn("needs.discover.result == 'success'", job)
        self.assertIn("uses: ./.github/workflows/runtime-promoted-catalog.yml", job)

    def test_token_capture_and_key_signer_are_separate_protected_jobs(self):
        source = CHILD.read_text()
        capture, sign = source.split("\n  sign:\n", 1)
        self.assertIn("  workflow_call:\n", capture)
        self.assertNotIn("  workflow_dispatch:\n", source)
        self.assertIn("environment: product-attestation", capture)
        self.assertIn("environment: product-attestation", sign)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", capture)
        self.assertNotIn("secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", capture)
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY: ${{ secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY }}", sign)
        self.assertNotIn("GITHUB_TOKEN:", sign)
        self.assertIn("needs: capture", sign)
        self.assertIn("CODEX_AGENT_RUNTIME_PROMOTION_CAPTURE_INVENTORY_SHA256", sign)
        self.assertLess(capture.index("runtime_catalog_promotion.py capture"),
                        capture.index("Retain the exact Runtime original"))
        self.assertLess(sign.index("Download independently approved Runtime capture"),
                        sign.index("runtime_catalog_promotion.py sign"))
        for command in ("./gradlew", "cargo build", "cmake --build", "xcodebuild", "npm run"):
            self.assertNotIn(command, source)


if __name__ == "__main__":
    unittest.main()
