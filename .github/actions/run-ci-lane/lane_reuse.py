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
  and logged, never treated as admitted;
* a receipt-first prefilter reads only ``lane-receipt.json`` and the selected
  inventory files of each candidate ZIP over ETag-pinned HTTP ranges, runs the
  unchanged legacy ``validate_receipt`` on that partial tree, and drops a
  candidate only when it fails a check that reads no other archive file (or
  restore's own receipt-field rules). Every other candidate, including any
  whose ranged read fails or whose layout could extract differently, stays in
  the list, in order, for the full legacy download.

Download digests, receipts, inventories, runner and toolchain checks and the
reissued transport receipt all stay in the legacy module, unchanged.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ci"))

RETRY_DELAYS = (1, 2, 4, 8, 16, 30, 30)
MAX_RATE_LIMIT_WAIT = 900
MAX_INDEX_PAGES = 1000
RECEIPT = "lane-receipt.json"
PREFILTER_MEMBER_BYTES = 64 * 1024**2
PREFILTER_WORKERS = 4
# Messages validate_receipt raises before it reads any archive file other than
# the receipt and the selected inventories. No other failure is ever a skip.
RECEIPT_LEVEL_REJECTIONS = (
    "Unsupported or non-exact lane receipt schema",
    "Lane receipt identity mismatch",
    "Lane receipt repository mismatch",
    "Reusable lane receipt is outside this PR scope",
    "Lane was not produced by a passing authoritative CI workflow",
    "Lane receipt artifact name mismatch",
    "Lane receipt runner identity mismatch",
    "Lane receipt toolchain identity mismatch",
    "Lane receipt validation action coverage is missing or malformed",
    "Lane receipt inventory set mismatch",
    "Lane validation action coverage mismatch:",
    "Lane production inventory mismatch",
    "Lane test inventory mismatch",
    "Lane metadata inventory mismatch",
)


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


def _ranged_archive(artifact, token):
    """The repository's ETag-pinned, bounded HTTP-range ZIP reader (no full download)."""
    import runtime_reference_archive
    return runtime_reference_archive.open_reference_archive(
        artifact, token, max_bytes=16 * 1024**3, max_members=65_536)


def receipt_members(infos, categories, inventory_names):
    """The receipt and selected inventory entries, or None when extraction could place other bytes there."""
    for info in infos:
        name = info.filename[:-1] if info.filename.endswith("/") else info.filename
        if (not name.isascii() or "\\" in name or name.startswith("/")
                or any(part in ("", ".", "..") for part in name.split("/"))):
            return None  # Extraction could normalize or alias this name.
    folded = [info.filename.rstrip("/").lower() for info in infos]
    hits = [info for info, name in zip(infos, folded) if RECEIPT in name.split("/")]
    if len(hits) != 1 or hits[0].is_dir() or PurePosixPath(hits[0].filename).name != RECEIPT:
        return None
    base = hits[0].filename[:-len(RECEIPT)]
    if RECEIPT in base.lower().split("/"):
        return None
    selected = [hits[0]]
    for category in categories:
        path = base + inventory_names[category]
        key = path.lower()
        matches = [info for info, name in zip(infos, folded) if name == key or name.startswith(key + "/")]
        if len(matches) != 1 or matches[0].filename != path or matches[0].is_dir():
            return None
        selected.append(matches[0])
    if any(info.file_size > PREFILTER_MEMBER_BYTES for info in selected):
        return None
    return selected


def receipt_verdict(legacy, artifact, token, *, plan, plan_path, lane, runner, toolchain, categories):
    """Return (skip, reason); skip is True only when the legacy gate certainly rejects the candidate."""
    try:
        legacy._artifact_transport_identity(artifact)
    except (KeyError, ValueError) as error:
        return False, f"transport identity left to legacy: {error}"
    promoted = bool(artifact.get("_promoted"))
    try:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "partial"
            with _ranged_archive(artifact, token) as (archive, _stream):
                selected = receipt_members(archive.infolist(), categories, legacy.INPUT_NAMES)
                if selected is None:
                    return False, "archive layout left to legacy"
                for info in selected:
                    target = root / Path(*PurePosixPath(info.filename).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(info))  # zipfile checks the size and CRC-32.
            receipt_path = root / Path(*PurePosixPath(selected[0].filename).parts)
            try:
                receipt = legacy.read_json(receipt_path)
            except ValueError as error:  # Undecodable or non-object receipt bytes.
                return True, f"receipt is unreadable: {type(error).__name__}"
            try:
                legacy.validate_receipt(
                    receipt_path, plan_path, receipt_path.parent, lane, allow_compatible=True,
                    allow_cross_pr=promoted, runner=runner, toolchain=toolchain, categories=categories)
            except ValueError as error:
                if type(error) is ValueError and str(error).startswith(RECEIPT_LEVEL_REJECTIONS):
                    return True, str(error)[:240]
            except Exception:  # noqa: BLE001 - never a skip; the legacy path decides.
                pass
    except Exception as error:  # noqa: BLE001 - any ranged failure keeps the full legacy path.
        return False, f"ranged read left to legacy: {type(error).__name__}"
    # restore() applies these receipt-field rules after a passing validation;
    # when they hold here they hold for the same receipt bytes there.
    try:
        if any(item["kind"] == "c-abi-sdk" for collection in ("artifacts", "evidence")
               for item in receipt[collection]) and (
                receipt["validationCommit"] != plan["validationCommit"]
                or receipt["validationTree"] != plan["validationTree"]):
            return True, "c-abi-sdk receipt is not this exact commit and tree"
        if not promoted and receipt["artifactName"] != artifact["name"]:
            return True, "receipt artifactName differs from the upload name"
    except Exception:  # noqa: BLE001 - malformed receipts are left to legacy.
        pass
    return False, "receipt-level checks pass"


def prefilter(legacy, arguments, rows, token):
    """Drop only candidates the unchanged legacy gate certainly rejects; keep the order."""
    started = time.monotonic()
    plan_path = arguments.plan.resolve()
    options = {
        "plan": legacy.read_json(plan_path),
        "plan_path": plan_path,
        "lane": arguments.lane,
        "runner": legacy.parse_mapping(arguments.runner) or None,
        "toolchain": legacy.parse_mapping(arguments.toolchain) or None,
        "categories": tuple(legacy.INPUT_NAMES) if arguments.mode == "full" else ("production",),
    }
    partial = f"codex-agent-ci-{arguments.lane}-production-"
    pending = [row for row in rows
               if not (arguments.mode == "full" and str(row.get("name", "")).startswith(partial))]
    with ThreadPoolExecutor(max_workers=PREFILTER_WORKERS) as pool:
        verdicts = dict(zip(map(id, pending), pool.map(
            lambda row: receipt_verdict(legacy, row, token, **options), pending)))
    kept = []
    for row in rows:
        skip, reason = verdicts.get(id(row), (False, "left to the legacy mode filter"))
        _log(f"receipt prefilter {'skipped' if skip else 'kept'} artifact {row.get('id')} "
             f"{row.get('name')}: {reason}")
        if not skip:
            kept.append(row)
    _log(f"receipt prefilter: {len(rows) - len(kept)} skipped, {len(kept)} kept for full legacy verification "
         f"in {time.monotonic() - started:.1f}s")
    return kept


def install(legacy, arguments=None):
    """Bind the retrying transport, indexed discovery and (with arguments) the receipt prefilter privately."""
    legacy.api_request = retrying(legacy.api_request)
    promoted = legacy.promoted_artifacts

    def candidates(api_url, repository, workflow, lane, pull_request, token, current_run):
        rows = indexed_candidates(legacy, api_url, repository, workflow, lane, pull_request, token, current_run)
        return rows if arguments is None else prefilter(legacy, arguments, rows, token)

    def promoted_candidates(api_url, repository, lane, token):
        rows = promoted(api_url, repository, lane, token)
        return rows if arguments is None else prefilter(legacy, arguments, rows, token)

    legacy.candidate_artifacts = candidates
    legacy.promoted_artifacts = promoted_candidates
    return legacy


def main() -> None:
    legacy = _legacy_module()
    arguments = legacy.parser().parse_args()
    install(legacy, arguments)
    value = legacy.restore(arguments)
    legacy.github_output(arguments.github_output, value)
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
