"""Real Git closure checks; no hosted, signing or publication evidence."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[2] / ".github/actions/prepare-runtime-signing/workflow_publication.py"
SPEC = importlib.util.spec_from_file_location("workflow_publication", PATH)
publication = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publication)


class ReviewedWorkflowPublicationTest(unittest.TestCase):
    def test_plan_resolves_native_publication_before_source_execution(self):
        root = PATH.parents[3]
        text = (root / ".github/workflows/product-validation.yml").read_text()
        plan = text.split("\n  plan:\n", 1)[1].split("\n  product:\n", 1)[0]
        self.assertIn("resolve-product-publication@reuse-authority", plan)
        for field in ("workflow_sha", "workflow_repository", "workflow_file_path"):
            self.assertIn("fromJSON(toJSON(job))." + field, plan)
        self.assertLess(plan.index("- id: publication"), plan.index("- id: impact"))
        self.assertIn("publisher_sha: ${{ steps.publication.outputs.publisher-sha", plan)
        self.assertIn("source_sha: ${{ steps.publication.outputs.source-sha", plan)
        lint = text.split("\n  workflow-lint:\n", 1)[1].split("\n  plan:\n", 1)[0]
        self.assertIn("ref: ${{ needs.plan.outputs.source_sha }}", lint)
        self.assertIn("TRUSTED_WORKFLOW_SHA: ${{ needs.plan.outputs.publisher_sha }}", lint)
        self.assertIn('--trusted-source-sha "$TRUSTED_SOURCE_SHA"', lint)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reviewed-workflow-publication-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git("init", "--quiet")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, files):
        for name, raw in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "--quiet", "-m", "reviewed closure")
        return self.git("rev-parse", "HEAD")

    def test_exact_recursive_closure_is_content_only_and_preserves_action_pins(self):
        entry = publication.ENTRYPOINT
        files = {entry: b"jobs:\n  child:\n    uses: ./.github/workflows/child.yml\n",
                 ".github/workflows/child.yml": (
                     b"jobs:\n  back:\n    uses: 'codex-agent-labs/codex-agent/"
                     b".github/workflows/product-validation.yml@reuse-authority'\n"
                     b"  action:\n    steps:\n      - uses: actions/checkout@" + b"a" * 40 + b" # retained pin\n")}
        sha = self.commit(files)
        result = publication.reviewed_workflow_closure(self.root, sha)
        self.assertEqual(files, result)
        inventory = publication.publication_inventory(result)
        self.assertEqual(sorted(files), [row["path"] for row in inventory])
        self.assertTrue(all(set(row) == {"path", "bytes", "sha256"} for row in inventory))

    def test_manual_unprotected_dynamic_and_escaped_references_fail_closed(self):
        for ref in ("a" * 40, "main", "${{ inputs.sha }}"):
            with self.subTest(ref=ref):
                sha = self.commit({publication.ENTRYPOINT: (
                    "jobs:\n  child:\n    uses: codex-agent-labs/codex-agent/"
                    ".github/workflows/child.yml@" + ref + "\n").encode()})
                with self.assertRaises(ValueError):
                    publication.reviewed_workflow_closure(self.root, sha)
        sha = self.commit({publication.ENTRYPOINT: b"jobs:\n  child:\n    uses: ./.github/workflows/../escape.yml\n"})
        with self.assertRaises(ValueError):
            publication.reviewed_workflow_closure(self.root, sha)
        for value in (">-", "*caller", "${{ inputs.workflow }}"):
            sha = self.commit({publication.ENTRYPOINT: ("jobs:\n  child:\n    uses: " + value + "\n").encode()})
            with self.subTest(value=value), self.assertRaises(ValueError):
                publication.reviewed_workflow_closure(self.root, sha)

    def test_missing_child_cannot_publish_a_partial_closure(self):
        sha = self.commit({publication.ENTRYPOINT: b"jobs:\n  child:\n    uses: ./.github/workflows/missing.yml\n"})
        with self.assertRaises((ValueError, subprocess.CalledProcessError)):
            publication.reviewed_workflow_closure(self.root, sha)

    def test_caller_closure_includes_other_statically_referenced_entrypoints(self):
        caller = ".github/workflows/ci.yml"
        other = ".github/workflows/sdk-failed-catalog-custody.yml"
        files = {
            publication.ENTRYPOINT: b"name: product\n",
            caller: ("jobs:\n  custody:\n    uses: codex-agent-labs/codex-agent/" + other
                     + "@reuse-authority\n").encode(),
            other: b"name: custody\n",
        }
        sha = self.commit(files)
        self.assertEqual(files, publication.reviewed_workflow_closure(
            self.root, sha, entrypoints=(publication.ENTRYPOINT, caller)))
