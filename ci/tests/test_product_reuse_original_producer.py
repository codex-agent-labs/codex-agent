"""An attestation run can name its already-completed CI producer explicitly."""

import unittest

from ci import product_reuse


PLAN = {
    "event": "pull_request", "repository": "codex-agent-labs/codex-agent",
    "validationCommit": "a" * 40, "validationTree": "b" * 40,
    "pullRequest": 31,
}


class OriginalProducerTest(unittest.TestCase):
    def test_explicit_original_is_not_current_attestation_run(self):
        producer = product_reuse._consumer(
            PLAN, {"GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "4"},
            original_run_id=41, original_run_attempt=2,
        )["producer"]
        self.assertEqual((41, 2), (producer["runId"], producer["runAttempt"]))
        self.assertEqual("a" * 40, producer["commit"])

    def test_partial_or_invalid_original_fails_closed(self):
        for options in ({"original_run_id": 41},
                        {"original_run_attempt": 2},
                        {"original_run_id": True, "original_run_attempt": 2},
                        {"original_run_id": 0, "original_run_attempt": 2}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                product_reuse._consumer(PLAN, {}, **options)


if __name__ == "__main__":
    unittest.main()
