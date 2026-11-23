"""Indexed, retrying lane-reuse discovery; the legacy admission gates stay unchanged."""
from __future__ import annotations

import hashlib
import importlib.util
from email.message import Message
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci/tests"))
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


LANE = "ios-rust-device"
PLAN_TREE = "b" * 40
TOOLCHAIN = {"cargo": "cargo 1.95.0", "rustc": "release=1.95.0", "xcode": "Xcode 26.6"}
RUNNER = {"arch": "ARM64", "image": "macos26", "imageVersion": "20261117.0516.1", "os": "macOS"}
INVENTORY = {"production": b"100644 blob p\tsrc/lib.rs\n", "test": b"100644 blob t\ttests/a.rs\n",
             "metadata": b"100644 blob m\tCargo.toml\n"}


class ReceiptPrefilterTest(unittest.TestCase):
    """The prefilter drops exactly candidates the unchanged legacy gate rejects."""

    def setUp(self):
        import tempfile
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plan_path = self.root / "build/ci/impact-plan.json"
        inventories = self.plan_path.parent / "inventories" / LANE
        inventories.mkdir(parents=True)
        self.legacy = lane_reuse._legacy_module()
        for category, filename in self.legacy.INPUT_NAMES.items():
            (inventories / filename).write_bytes(INVENTORY[category])
        self.plan = {"repository": REPOSITORY, "pullRequest": 31, "event": "pull_request",
                     "baseCommit": "1" * 40, "headCommit": "2" * 40, "validationCommit": "3" * 40,
                     "validationTree": PLAN_TREE,
                     "lanes": {LANE: {"build": True, "test": True, "metadata": True, "reuseAllowed": True}}}
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")
        self.archives, self.downloads, self.ranges = {}, [], []
        self.range_override = {}
        import receipt as receipt_module
        import runtime_reference_archive
        for target in (patch.object(receipt_module, "validate_legacy_lane_projection", lambda *a, **k: None),
                       patch.object(runtime_reference_archive, "_Archive", side_effect=self.range_reader),
                       patch.dict("os.environ", {"GITHUB_RUN_ID": "777", "GITHUB_RUN_ATTEMPT": "1"}),
                       patch("sys.stderr", new_callable=io.StringIO)):
            target.start()
            self.addCleanup(target.stop)
        self.next_id = 1000

    # -- fixtures -------------------------------------------------------------------------------
    def receipt(self, name, **changes):
        payload = self.payload()
        value = {"schemaVersion": 2, "repository": REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
                 "event": "pull_request", "runId": 5, "runAttempt": 1, "pullRequest": 31,
                 "baseCommit": "4" * 40, "headCommit": "5" * 40, "validationCommit": "6" * 40,
                 "validationTree": "7" * 40, "lane": LANE, "artifactName": name, "runner": dict(RUNNER),
                 "toolchain": {**TOOLCHAIN, "validationActions": "build,metadata,test"},
                 "inputFiles": dict(self.legacy.INPUT_NAMES),
                 "artifacts": [{"relativePath": "payload/librust.a", "kind": "rust-archive",
                                "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}],
                 "evidence": [], "result": "passed"}
        value.update(changes)
        return value

    @staticmethod
    def payload():
        return b"".join(hashlib.sha256(f"payload:{index}".encode()).digest() for index in range(64))

    def artifact(self, *, receipt=None, name=None, members=None, raw=None, promoted=False, prefix=""):
        self.next_id += 1
        identifier = self.next_id
        name = name or f"codex-agent-ci-{LANE}-{identifier:040d}"
        if raw is None:
            receipt = receipt if receipt is not None else self.receipt(name)
            files = {"lane-receipt.json": json.dumps(receipt, indent=2).encode(),
                     "payload/librust.a": self.payload(),
                     **{filename: INVENTORY[category] for category, filename in self.legacy.INPUT_NAMES.items()}}
            if members is not None:
                files = members(files)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for path, data in files.items():
                    archive.writestr(prefix + path, data)
            raw = buffer.getvalue()
        url = f"{API}/repos/{REPOSITORY}/actions/artifacts/{identifier}/zip"
        self.archives[url] = raw
        row = {"id": identifier, "name": name, "expired": False, "size_in_bytes": len(raw),
               "digest": "sha256:" + hashlib.sha256(raw).hexdigest(), "archive_download_url": url,
               "workflow_run": {"id": 9}}
        return {**row, "_promoted": True} if promoted else row

    def range_reader(self, artifact, token, **kwargs):
        from range_archive_support import BytesRangeArchive
        url = artifact["archive_download_url"]
        owner = types.SimpleNamespace(raw=self.archives[url], range_etag='"e"', range_readers=0, range_bytes=0)
        override = self.range_override.get(url)
        owner.range_body = override or (lambda begin, size: owner.raw[begin:begin + size])
        self.ranges.append(url)
        return BytesRangeArchive(owner, artifact, token, **kwargs)

    def api_request(self, url, token):
        self.downloads.append(url)
        return self.archives[url]

    def arguments(self, mode, destination):
        from argparse import Namespace
        return Namespace(plan=self.plan_path, lane=LANE, destination=self.root / destination, mode=mode,
                         workflow="ci.yml", runner=[f"{k}={v}" for k, v in RUNNER.items()],
                         toolchain=[f"{k}={v}" for k, v in TOOLCHAIN.items()], token="token", api_url=API,
                         github_output=None)

    def legacy_restore(self, rows, mode, destination, promoted=()):
        legacy = lane_reuse._legacy_module()
        legacy.validate_legacy_lane_projection = lambda *args, **kwargs: None  # Plan-level; same for both.
        legacy.api_request = self.api_request
        legacy.candidate_artifacts = lambda *args: [row for row in rows]
        legacy.promoted_artifacts = lambda *args: [row for row in promoted]
        return legacy.restore(self.arguments(mode, destination))

    def wrapped_restore(self, rows, mode, destination, promoted=()):
        legacy = lane_reuse._legacy_module()
        legacy.validate_legacy_lane_projection = lambda *args, **kwargs: None  # Plan-level; same for both.
        legacy.api_request = self.api_request
        legacy.promoted_artifacts = lambda *args: [row for row in promoted]
        arguments = self.arguments(mode, destination)
        lane_reuse.install(legacy, arguments)
        with patch.object(lane_reuse, "indexed_candidates", return_value=[row for row in rows]):
            return legacy.restore(arguments)

    def verdict(self, row, mode):
        legacy = lane_reuse._legacy_module()
        return lane_reuse.receipt_verdict(
            legacy, row, "token", plan=self.plan, plan_path=self.plan_path.resolve(), lane=LANE,
            runner=dict(RUNNER), toolchain=dict(TOOLCHAIN),
            categories=tuple(legacy.INPUT_NAMES) if mode == "full" else ("production",))

    def variants(self):
        name = f"codex-agent-ci-{LANE}-" + "9" * 40
        inventory = self.legacy.INPUT_NAMES

        def replace(path, data):
            return lambda files: {**files, path: data}

        def duplicate(files):
            return {**files, "nested/lane-receipt.json": files["lane-receipt.json"]}

        def drop(path):
            return lambda files: {key: value for key, value in files.items() if key != path}

        return {
            # expected skip in (full, production), legacy admission in (full, production)
            "compatible": (self.artifact(), (False, False), (True, True)),
            "compatible-nested": (self.artifact(prefix="build/ci/lane/"), (False, False), (True, True)),
            "promoted-other-pr": (self.artifact(receipt=self.receipt(name, pullRequest=7), promoted=True),
                                  (False, False), (True, True)),
            "incompatible-runner": (self.artifact(receipt=self.receipt(
                name, runner={**RUNNER, "imageVersion": "20260728.0273.1"}), name=name),
                (True, True), (False, False)),
            "incompatible-toolchain": (self.artifact(receipt=self.receipt(
                name, toolchain={**TOOLCHAIN, "cargo": "cargo 1.94.0", "validationActions": "build,metadata,test"}),
                name=name), (True, True), (False, False)),
            "production-inventory-mismatch": (self.artifact(members=replace(inventory["production"], b"other\n")),
                                              (True, True), (False, False)),
            "test-inventory-mismatch": (self.artifact(members=replace(inventory["test"], b"other\n")),
                                        (True, False), (False, True)),
            "missing-inventory": (self.artifact(members=drop(inventory["metadata"])), (False, False), (False, False)),
            "action-coverage": (self.artifact(receipt=self.receipt(
                name, toolchain={**TOOLCHAIN, "validationActions": "build"}), name=name),
                (True, False), (False, True)),
            "wrong-name": (self.artifact(receipt=self.receipt(f"codex-agent-ci-{LANE}-" + "8" * 40)),
                           (True, True), (False, False)),
            "wrong-pr": (self.artifact(receipt=self.receipt(name, pullRequest=30), name=name),
                         (True, True), (False, False)),
            "schema": (self.artifact(receipt={**self.receipt(name), "extra": 1}, name=name), (True, True), (False, False)),
            "c-abi-tree-mismatch": (self.artifact(receipt=self.receipt(name, artifacts=[
                {**self.receipt(name)["artifacts"][0], "kind": "c-abi-sdk"}]), name=name), (True, True), (False, False)),
            "c-abi-exact-tree": (self.artifact(receipt=self.receipt(name, artifacts=[
                {**self.receipt(name)["artifacts"][0], "kind": "c-abi-sdk"}], validationCommit="3" * 40,
                validationTree=PLAN_TREE), name=name), (False, False), (True, True)),
            "receipt-not-json": (self.artifact(members=replace("lane-receipt.json", b"{not json")),
                                 (True, True), (False, False)),
            "payload-integrity": (self.artifact(members=replace("payload/librust.a", b"tampered")),
                                  (False, False), (False, False)),
            "two-receipts": (self.artifact(members=duplicate), (False, False), (False, False)),
        }

    # -- properties -----------------------------------------------------------------------------
    def test_every_skip_is_a_legacy_rejection_over_fixture_receipts(self):
        for label, (row, expected_skip, expected_admission) in self.variants().items():
            for index, mode in enumerate(("full", "production")):
                with self.subTest(label=label, mode=mode):
                    skip, reason = self.verdict(row, mode)
                    legacy = self.legacy_restore([row], mode, f"{label}-{mode}-legacy")
                    self.assertEqual(expected_admission[index], legacy["reused"], legacy)
                    self.assertEqual(expected_skip[index], skip, reason)
                    if skip:  # The invariant: a skip is only ever a certain legacy rejection.
                        self.assertFalse(legacy["reused"])
                    wrapped = self.wrapped_restore([row], mode, f"{label}-{mode}-wrapped")
                    self.assertEqual(legacy, wrapped)

    def test_malformed_or_unreadable_archives_fall_back_to_the_full_legacy_path(self):
        compatible = self.artifact()
        broken = self.artifact(raw=b"not a zip archive at all")
        self.range_override[compatible["archive_download_url"]] = lambda begin, size: (_ for _ in ()).throw(
            urllib.error.URLError(ConnectionError("reset")))
        self.assertEqual(False, self.verdict(compatible, "full")[0])
        self.assertEqual(False, self.verdict(broken, "full")[0])
        malformed_digest = {**self.artifact(), "digest": "sha256:xyz"}
        self.assertEqual((False, "transport identity left to legacy: GitHub artifact transport digest is malformed"),
                         self.verdict(malformed_digest, "full"))
        self.assertTrue(self.wrapped_restore([compatible], "full", "fallback")["reused"])
        self.assertEqual([compatible["archive_download_url"]], self.downloads)
        # A non-ZIP body escapes the legacy gate as BadZipFile; the wrapper keeps that behaviour.
        for restore in (self.legacy_restore, self.wrapped_restore):
            with self.assertRaises(zipfile.BadZipFile):
                restore([broken], "full", f"broken-{restore.__name__}")
        # A malformed transport digest still aborts the whole lookup exactly as before.
        self.assertEqual(self.legacy_restore([malformed_digest, compatible], "full", "digest-legacy"),
                         self.wrapped_restore([malformed_digest, compatible], "full", "digest-wrapped"))

    def test_admitted_tree_is_byte_identical_and_rejected_bodies_are_never_downloaded(self):
        variants = self.variants()
        rows = [variants[label][0] for label in (
            "incompatible-runner", "incompatible-toolchain", "wrong-name", "payload-integrity",
            "c-abi-tree-mismatch", "compatible", "compatible-nested")]
        for mode in ("full", "production"):
            with self.subTest(mode=mode):
                self.downloads.clear()
                legacy = self.legacy_restore(rows, mode, f"identity-{mode}-legacy")
                legacy_downloads = list(self.downloads)
                self.downloads.clear()
                wrapped = self.wrapped_restore(rows, mode, f"identity-{mode}-wrapped")
                self.assertTrue(legacy["reused"])
                self.assertEqual(legacy, wrapped)
                self.assertEqual(self.tree(self.root / f"identity-{mode}-legacy"),
                                 self.tree(self.root / f"identity-{mode}-wrapped"))
                self.assertEqual([row["archive_download_url"] for row in rows[:6]], legacy_downloads)
                self.assertEqual([row["archive_download_url"] for row in (rows[3], rows[5])], self.downloads)

    def test_full_mode_never_prefilters_production_partial_uploads(self):
        partial = self.artifact(name=f"codex-agent-ci-{LANE}-production-" + "1" * 40)
        self.ranges.clear()
        self.assertFalse(self.wrapped_restore([partial], "full", "partial")["reused"])
        self.assertEqual([], self.ranges)
        self.assertEqual([], self.downloads)

    def test_inconsistent_ranged_bytes_fail_closed(self):
        """Ranged bytes only steer the order of work: a forged compatible view still meets the full
        legacy gate on the digest-checked download, and a forged incompatible view can only cost a
        rebuild, never admit anything."""
        name = f"codex-agent-ci-{LANE}-" + "9" * 40
        incompatible = self.artifact(receipt=self.receipt(name, runner={**RUNNER, "os": "Linux"}), name=name)
        forged_compatible = self.archives[self.artifact(name=name)["archive_download_url"]]
        incompatible["size_in_bytes"] = len(forged_compatible)  # Legacy checks only the digest.
        self.range_override[incompatible["archive_download_url"]] = (
            lambda begin, size: forged_compatible[begin:begin + size])
        self.assertEqual((False, "receipt-level checks pass"), self.verdict(incompatible, "full"))
        self.downloads.clear()
        legacy = self.legacy_restore([incompatible], "full", "forged-compatible-legacy")
        wrapped = self.wrapped_restore([incompatible], "full", "forged-compatible-wrapped")
        self.assertFalse(wrapped["reused"])
        self.assertEqual(legacy, wrapped)
        self.assertEqual([incompatible["archive_download_url"]] * 2, self.downloads)

        compatible = self.artifact(name=f"codex-agent-ci-{LANE}-" + "6" * 40)
        forged_incompatible = self.archives[self.artifact(receipt=self.receipt(
            compatible["name"], runner={**RUNNER, "os": "Linux"}), name=compatible["name"])["archive_download_url"]]
        compatible["size_in_bytes"] = len(forged_incompatible)
        self.range_override[compatible["archive_download_url"]] = (
            lambda begin, size: forged_incompatible[begin:begin + size])
        self.downloads.clear()
        wrapped = self.wrapped_restore([compatible], "full", "forged-incompatible")
        self.assertEqual("no-compatible-artifact", wrapped["reason"])
        self.assertFalse(wrapped["reused"])
        self.assertEqual([], self.downloads)
        self.assertFalse((self.root / "forged-incompatible").exists())

    @staticmethod
    def tree(root):
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*"))
                if path.is_file()}


if __name__ == "__main__":
    unittest.main()
