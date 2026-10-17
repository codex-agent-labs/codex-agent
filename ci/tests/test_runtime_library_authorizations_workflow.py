"""Static custody checks only; protected approvals and hosted bytes are not simulated."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci import product_reuse
from ci.tests.test_contract_attestation_workflow import workflow_job
from ci.products.inventory import sha256_file


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/runtime-library-authorizations.yml"


class RuntimeLibraryAuthorizationsWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.delegate = workflow_job(cls.source, "delegate")
        cls.capture = workflow_job(cls.source, "capture")
        cls.authorize = workflow_job(cls.source, "authorize")

    def test_uncalled_protected_jobs_have_distinct_private_keys(self):
        self.assertIn("  workflow_call:", self.source)
        self.assertNotIn("  workflow_dispatch:", self.source)
        self.assertIn("environment: sdk-runtime-root-attestation", self.delegate)
        self.assertIn("environment: product-attestation", self.authorize)
        self.assertNotIn("    environment:", self.capture)
        self.assertIn("secrets.CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY", self.delegate)
        self.assertNotIn("secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", self.delegate)
        self.assertNotIn("GITHUB_TOKEN:", self.delegate)
        self.assertNotIn("secrets.", self.capture)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", self.capture)
        self.assertIn("secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", self.authorize)
        self.assertNotIn("secrets.CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY", self.authorize)
        self.assertNotIn("GITHUB_TOKEN:", self.authorize)

    def test_control_is_independently_approved_in_both_protected_environments(self):
        for job in (self.delegate, self.authorize):
            self.assertIn("vars.CODEX_AGENT_RUNTIME_PHASE10_CONTROL_APPROVED_SHA256", job)
            self.assertIn("vars.CODEX_AGENT_PRODUCT_TRUSTED_SOURCE_SHA", job)
            self.assertIn("vars.CODEX_AGENT_SDK_RUNTIME_ROOT_PUBLIC_KEY_SHA256", job)
            self.assertIn("sha256sum", job)
            self.assertIn("persist-credentials: false", job)
        self.assertIn("CODEX_AGENT_PRODUCT_KEYRING_SHA256", self.delegate)
        self.assertIn("CODEX_AGENT_PRODUCT_KEYS_INVENTORY_SHA256", self.delegate)
        self.assertIn("runtime_phase10_library_caller.py delegate", self.delegate)
        self.assertIn("runtime_phase10_library_caller.py authorize", self.authorize)
        self.assertIn("--expected-delegation-inventory-sha256", self.authorize)

    def test_original_capture_is_token_only_and_pinned_before_release_signing(self):
        self.assertIn("needs: delegate", self.capture)
        self.assertIn("needs: [delegate, capture]", self.authorize)
        self.assertIn("products._download_contract_ci_upload(", self.capture)
        self.assertIn("verified_zip_contents(", self.capture)
        self.assertIn("safe_extract(archive, Path('plan'))", self.capture)
        self.assertLess(self.capture.index("products._download_contract_ci_upload("),
                        self.capture.index("safe_extract(archive, Path('plan'))"))
        self.assertIn("regular_file_inventory(Path('plan'), allow_empty=True) != files", self.capture)
        self.assertIn("git -C validation-source rev-parse 'HEAD^{tree}'", self.capture)
        self.assertIn("--original-run-id", self.capture)
        self.assertIn("--original-run-attempt", self.capture)
        self.assertIn("--trusted-workflow-sha", self.capture)
        self.assertIn("runtime_phase10_upload_locator.py", self.capture)
        self.assertIn("--expected-build-key", self.capture)
        self.assertIn("--expected-metadata-receipt-sha256", self.capture)
        self.assertIn("regular_file_inventory(Path(sys.argv[1]), allow_empty=True)", self.authorize)
        self.assertIn("--protected-output capture/original", self.authorize)
        self.assertIn("--root-delegation delegation", self.authorize)
        for job in (self.delegate, self.capture, self.authorize):
            self.assertIn("overwrite: false", job)
            self.assertIn("if-no-files-found: error", job)
            self.assertIn("include-hidden-files: true", job)

    def test_substituted_plan_zip_fails_approved_digest_before_extraction(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-plan-zip-") as temporary:
            root = Path(temporary)
            original = root / "original.zip"
            substitute = root / "substitute.zip"
            with zipfile.ZipFile(original, "w") as archive:
                archive.writestr("impact-plan.json", b"approved")
            with zipfile.ZipFile(substitute, "w") as archive:
                archive.writestr("impact-plan.json", b"replaced")
            self.assertEqual(original.stat().st_size, substitute.stat().st_size)
            digest = sha256_file(original)
            artifact_id, run_id = 17, 23
            commit, tree = "a" * 40, "b" * 40
            name = f"codex-agent-ci-plan-{tree}"
            url = f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/{artifact_id}"
            detail = {"id": artifact_id, "digest": digest, "expired": False,
                      "name": name, "archive_download_url": url + "/zip",
                      "workflow_run": {"id": run_id, "head_sha": commit},
                      "size_in_bytes": original.stat().st_size}
            with patch.object(product_reuse, "api_json", return_value=detail), \
                    patch.object(product_reuse, "download_artifact_to_file",
                                 side_effect=lambda _artifact, _token, destination, **_kwargs:
                                 destination.write_bytes(substitute.read_bytes())):
                with self.assertRaisesRegex(ValueError, "bytes differ"):
                    product_reuse._download_contract_ci_upload(
                        artifact_id, digest, name, {"runId": run_id},
                        {"head_sha": commit}, "test-observation-token",
                        destination=root / "downloaded.zip", max_bytes=1024 * 1024)


if __name__ == "__main__":
    unittest.main()
