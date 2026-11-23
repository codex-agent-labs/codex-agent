"""Run the unchanged legacy lane-reuse gates over one bounded repository artifact index.

The legacy lookup lists every completed pull-request run and then every run's
artifacts: about a thousand unretried API calls per lane. Parallel lanes
exhaust the shared token quota, and one HTTP error aborts discovery. This
wrapper only changes how candidates are found and how transient GETs recover:

* candidates come from one repository artifact index, filtered to this lane;
* each candidate run is freshly observed with the same identity filters the
  legacy run listing applied (completed pull_request run of this workflow,
  this PR, not the current run);
* transient GETs retry; one candidate run that cannot be observed is skipped
  and logged, never treated as admitted.

Download digests, receipts, inventories, runner and toolchain checks and the
reissued transport receipt all stay in the legacy module, unchanged.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ci"))

RETRY_DELAYS = (1, 2, 4, 8, 16, 30, 30)
MAX_RATE_LIMIT_WAIT = 900
MAX_INDEX_PAGES = 1000


def _legacy_module():
    spec = importlib.util.spec_from_file_location("lane_reuse_legacy_lookup", ROOT / "ci/reuse.py")
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    return legacy


def _log(message: str) -> None:
    print(f"lane-reuse: {message}", file=sys.stderr, flush=True)


def _redacted(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _rate_limit_delay(error: urllib.error.HTTPError, now: float) -> float | None:
    """Wait only on an explicit GitHub quota or secondary-limit response."""
    if error.code not in {403, 429} or not error.headers:
        return None
    retry_after = error.headers.get("retry-after")
    if isinstance(retry_after, str) and re.fullmatch(r"[0-9]{1,4}", retry_after):
        return float(retry_after) + 1
    remaining, reset = error.headers.get("x-ratelimit-remaining"), error.headers.get("x-ratelimit-reset")
    if (isinstance(remaining, str) and remaining == "0" and isinstance(reset, str)
            and re.fullmatch(r"[0-9]{1,20}", reset)):
        delay = int(reset) - now
        if -5 <= delay <= 3600:
            return max(0.0, delay) + 2
    return None


def retrying(operation, *, delays=RETRY_DELAYS, sleep=time.sleep, clock=time.time):
    """Retry transient GitHub GETs; every attempt keeps the caller's full checks."""
    def call(url, *args, **kwargs):
        waited = 0.0
        for attempt in range(len(delays) + 1):
            try:
                return operation(url, *args, **kwargs)
            except urllib.error.HTTPError as error:
                status = error.code
                delay = _rate_limit_delay(error, clock())
                transient = status in {500, 502, 503, 504} or delay is not None
                _log(f"HTTP {status} for {_redacted(url)} (attempt {attempt + 1})")
                error.close()
                if not transient or attempt == len(delays):
                    raise
                if delay is not None:
                    if waited + delay > MAX_RATE_LIMIT_WAIT:
                        raise
                    waited += delay
                    _log(f"waiting {delay:.0f}s for the GitHub rate limit")
                    sleep(delay)
                else:
                    sleep(delays[attempt])
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                _log(f"{type(error).__name__} for {_redacted(url)} (attempt {attempt + 1}): {error}")
                if attempt == len(delays):
                    raise
                sleep(delays[attempt])
        raise AssertionError("unreachable")
    return call


def repository_artifacts(legacy, api_url: str, repository: str, token: str) -> list[dict]:
    """One complete repository artifact index; duplicates from page shifts are merged."""
    url = f"{api_url}/repos/{repository}/actions/artifacts"
    rows, seen = [], set()
    for page in range(1, MAX_INDEX_PAGES + 1):
        value = legacy.api_json(f"{url}?per_page=100&page={page}", token)
        batch = value.get("artifacts")
        if not isinstance(batch, list):
            raise ValueError("GitHub artifact index is missing artifacts")
        for row in batch:
            if not isinstance(row, dict) or type(row.get("id")) is not int:
                raise ValueError("GitHub artifact index has a malformed row")
            if row["id"] not in seen:
                seen.add(row["id"])
                rows.append(row)
        if len(batch) < 100:
            return rows
    raise ValueError("GitHub artifact index exceeds its page bound")


def indexed_candidates(legacy, api_url, repository, workflow, lane, pull_request, token, current_run):
    """Same admission filters as the legacy run listing, from one artifact index."""
    prefix = f"codex-agent-ci-{lane}-"
    rows = [row for row in repository_artifacts(legacy, api_url, repository, token)
            if row.get("expired") is False
            and isinstance(row.get("name"), str) and row["name"].startswith(prefix)
            and isinstance(row.get("archive_download_url"), str)
            and isinstance(row.get("workflow_run"), dict)
            and type(row["workflow_run"].get("id")) is int
            and row["workflow_run"]["id"] != current_run]
    expected_path = workflow if workflow.startswith(".github/workflows/") else ".github/workflows/" + workflow
    accepted, skipped = {}, 0
    for run_id in sorted({row["workflow_run"]["id"] for row in rows}, reverse=True):
        try:
            run = legacy.api_json(f"{api_url}/repos/{repository}/actions/runs/{run_id}", token)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            skipped += 1
            _log(f"skipping candidate run {run_id}: {type(error).__name__}"
                 + (f" HTTP {error.code}" if isinstance(error, urllib.error.HTTPError) else ""))
            continue
        if (run.get("id") == run_id and run.get("event") == "pull_request"
                and run.get("status") == "completed" and run.get("path") == expected_path
                and legacy.run_matches_pr(run, pull_request)):
            accepted[run_id] = run
    _log(f"{len(rows)} indexed {lane} uploads, {len(accepted)} candidate runs, {skipped} unobservable runs")
    return sorted((row for row in rows if row["workflow_run"]["id"] in accepted),
                  key=lambda row: (str(accepted[row["workflow_run"]["id"]].get("created_at", "")),
                                   row["workflow_run"]["id"], row["id"]), reverse=True)


def install(legacy):
    """Bind the retrying transport and indexed discovery inside this private module only."""
    legacy.api_request = retrying(legacy.api_request)

    def candidates(api_url, repository, workflow, lane, pull_request, token, current_run):
        return indexed_candidates(legacy, api_url, repository, workflow, lane, pull_request, token, current_run)

    legacy.candidate_artifacts = candidates
    return legacy


def main() -> None:
    legacy = install(_legacy_module())
    arguments = legacy.parser().parse_args()
    value = legacy.restore(arguments)
    legacy.github_output(arguments.github_output, value)
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
