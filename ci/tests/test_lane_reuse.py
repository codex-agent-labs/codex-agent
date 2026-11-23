"""Indexed, retrying lane-reuse discovery; the legacy admission gates stay unchanged."""
from __future__ import annotations

import importlib.util
from email.message import Message
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("lane_reuse_under_test", ROOT / ".github/actions/run-ci-lane/lane_reuse.py")
lane_reuse = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lane_reuse)

API = "https://api.github.com"
REPOSITORY = "codex-agent-labs/codex-agent"


def http_error(code, headers=None):
    message = Message()
    for name, value in (headers or {}).items():
        message[name] = value
    return urllib.error.HTTPError(f"{API}/x", code, "synthetic", message, io.BytesIO(b"{}"))


def run(run_id, **changes):
    return {"id": run_id, "event": "pull_request", "status": "completed", "path": ".github/workflows/ci.yml",
            "pull_requests": [{"number": 31}], "created_at": f"2026-11-{run_id:02d}T00:00:00Z", **changes}


def artifact(artifact_id, run_id, name="codex-agent-ci-desktop-linux-arm64-" + "a" * 40, **changes):
    return {"id": artifact_id, "name": name, "expired": False, "digest": "sha256:" + "0" * 64,
            "archive_download_url": f"{API}/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip",
            "workflow_run": {"id": run_id}, **changes}


class RetryTest(unittest.TestCase):
    def setUp(self):
        self.sleeps = []

    def call(self, responses, **kwargs):
        sequence = list(responses)

        def operation(url, token):
            value = sequence.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value

        with patch("sys.stderr", new_callable=io.StringIO) as stderr:
            try:
                return lane_reuse.retrying(operation, sleep=self.sleeps.append, clock=lambda: 1000.0,
                                           **kwargs)(f"{API}/repos/x", "token"), stderr.getvalue()
            except Exception as error:  # noqa: BLE001 - surfaced to the assertion below.
                return error, stderr.getvalue()

    def test_server_errors_and_connection_failures_retry_then_succeed(self):
        value, log = self.call([http_error(502), ConnectionError("reset"), b"body"])
        self.assertEqual(b"body", value)
        self.assertEqual([1, 2], self.sleeps)
        self.assertIn("HTTP 502", log)

    def test_rate_limit_waits_for_reset_or_retry_after(self):
        value, log = self.call([http_error(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1010"}),
                                http_error(429, {"retry-after": "7"}), b"body"])
        self.assertEqual(b"body", value)
        self.assertEqual([12.0, 8.0], self.sleeps)
        self.assertIn("HTTP 403", log)
        self.assertIn("rate limit", log)

    def test_real_failures_are_not_retried_and_report_their_status(self):
        for code in (401, 404, 410, 422):
            with self.subTest(code=code):
                self.sleeps.clear()
                error, log = self.call([http_error(code), b"never"])
                self.assertIsInstance(error, urllib.error.HTTPError)
                self.assertEqual(code, error.code)
                self.assertEqual([], self.sleeps)
                self.assertIn(f"HTTP {code}", log)
        error, _ = self.call([http_error(403), b"never"])  # Forbidden without quota headers.
        self.assertEqual(403, error.code)

    def test_exhausted_retries_and_excessive_rate_limit_waits_raise(self):
        error, _ = self.call([http_error(503)] * 3, delays=(1, 1))
        self.assertEqual(503, error.code)
        self.assertEqual([1, 1], self.sleeps)
        self.sleeps.clear()
        error, _ = self.call([http_error(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "4000"})])
        self.assertEqual(403, error.code)
        self.assertEqual([], self.sleeps)


class IndexedCandidateTest(unittest.TestCase):
    def setUp(self):
        self.legacy = lane_reuse._legacy_module()
        self.pages = [[artifact(index, 9) for index in range(100, 200)],
                      [artifact(5, 7), artifact(6, 8), artifact(7, 3), artifact(8, 4), artifact(9, 5),
                       artifact(10, 6), artifact(11, 10), artifact(199, 9),
                       artifact(12, 7, expired=True), artifact(13, 7, name="codex-agent-ci-desktop-linux-x64-x"),
                       artifact(14, 12), artifact(15, 2, archive_download_url=None)]]
        self.runs = {9: run(9), 7: run(7), 8: run(8, pull_requests=[{"number": 30}]), 3: run(3, event="push"),
                     4: run(4, status="in_progress"), 5: run(5, path=".github/workflows/promote.yml"),
                     6: urllib.error.HTTPError(f"{API}/runs/6", 404, "gone", Message(), io.BytesIO(b"")),
                     10: run(10, id=99), 2: run(2)}
        self.requests = []

        def api_json(url, token):
            self.requests.append(url)
            if "/actions/artifacts?" in url:
                page = int(url.rsplit("page=", 1)[1])
                return {"total_count": 112, "artifacts": self.pages[page - 1] if page <= len(self.pages) else []}
            value = self.runs[int(url.rsplit("/", 1)[1])]
            if isinstance(value, BaseException):
                raise value
            return value

        self.legacy.api_json = api_json

    def candidates(self):
        with patch("sys.stderr", new_callable=io.StringIO) as stderr:
            values = lane_reuse.indexed_candidates(self.legacy, API, REPOSITORY, "ci.yml", "desktop-linux-arm64",
                                                   31, "token", 12)
        return values, stderr.getvalue()

    def test_only_this_prs_completed_ci_runs_survive_and_unobservable_runs_are_skipped(self):
        values, log = self.candidates()
        self.assertEqual({9, 7}, {value["workflow_run"]["id"] for value in values})
        self.assertEqual(101, len(values))  # The shifted duplicate 199 appears once.
        self.assertEqual([9] * 100 + [7], [value["workflow_run"]["id"] for value in values])
        self.assertEqual(sorted((value["id"] for value in values if value["workflow_run"]["id"] == 9), reverse=True),
                         [value["id"] for value in values[:100]])
        self.assertIn("skipping candidate run 6: HTTPError HTTP 404", log)
        # One index (two pages) plus one observation per distinct candidate run, never per-run listings.
        self.assertEqual(2, sum("/actions/artifacts?" in url for url in self.requests))
        self.assertFalse(any(url.endswith("/artifacts") for url in self.requests))
        self.assertNotIn(f"{API}/repos/{REPOSITORY}/actions/runs/12", self.requests)

    def test_malformed_or_unbounded_index_fails_discovery_closed(self):
        self.pages[1].append({"id": "not-an-integer"})
        with self.assertRaises(ValueError):
            self.candidates()
        self.pages[1].pop()
        with patch.object(lane_reuse, "MAX_INDEX_PAGES", 1), self.assertRaises(ValueError):
            self.candidates()

    def test_install_keeps_legacy_admission_and_wraps_only_transport_and_discovery(self):
        legacy = lane_reuse._legacy_module()
        validate, download, restore = legacy.validate_receipt, legacy.download_artifact, legacy.restore
        original = legacy.api_request
        lane_reuse.install(legacy)
        self.assertIs(validate, legacy.validate_receipt)
        self.assertIs(download, legacy.download_artifact)
        self.assertIs(restore, legacy.restore)
        self.assertIsNot(original, legacy.api_request)
        self.assertEqual("candidates", legacy.candidate_artifacts.__name__)
        # The shared importable ci/reuse.py module is never modified.
        import reuse
        self.assertIsNot(reuse, legacy)
        self.assertEqual("candidate_artifacts", reuse.candidate_artifacts.__name__)


if __name__ == "__main__":
    unittest.main()
