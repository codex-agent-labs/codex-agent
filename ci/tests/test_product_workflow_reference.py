"""Exact workflow authority selection preserves unrelated original references."""
import copy
import unittest

import product_reuse


class ProductWorkflowReferenceTest(unittest.TestCase):
    path = "codex-agent-labs/codex-agent/.github/workflows/runtime-library-authorizations.yml"
    sha = "3cd56a3e2fdb4fa7d01832d7f136ef3d79c10b6b"

    def exact(self):
        return {"path": self.path + "@" + self.sha, "sha": self.sha}

    def protected(self, sha):
        return {"path": self.path + "@reuse-authority", "sha": sha,
                "ref": "refs/heads/reuse-authority"}

    def verify(self, references):
        run = {"referenced_workflows": references}
        before = copy.deepcopy(run)
        try:
            product_reuse._require_ci_workflow_reference(run, self.path + "@" + self.sha, self.sha)
        finally:
            self.assertEqual(before, run)

    def test_exact_revision_coexists_with_legacy_and_other_revisions(self):
        self.verify([self.protected("b0457bf4990d118b1de1afffad4905e63cc0f059"), self.exact(),
                     {"path": self.path + "@" + "a" * 40, "sha": "a" * 40}])

    def test_protected_branch_requires_the_exact_resolved_revision_and_ref(self):
        self.verify([self.protected(self.sha), {"path": self.path + "@" + "a" * 40, "sha": "a" * 40}])
        for change in ({"sha": "a" * 40}, {"ref": "refs/heads/unreviewed"},
                       {"path": "other/repository/.github/workflows/runtime-library-authorizations.yml@reuse-authority"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.verify([{**self.protected(self.sha), **change}])

    def test_missing_wrong_or_ambiguous_exact_identity_rejects(self):
        cases = [[], [{**self.exact(), "sha": "a" * 40}],
                 [{**self.exact(), "path": self.path + "@unreviewed"}],
                 [{**self.exact(), "path": "other/repository/.github/workflows/runtime-library-authorizations.yml@" + self.sha}],
                 [self.exact(), self.exact()], [self.exact(), self.protected(self.sha)]]
        for references in cases:
            with self.subTest(references=references), self.assertRaises(ValueError):
                self.verify(references)


if __name__ == "__main__":
    unittest.main()
