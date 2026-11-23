#!/usr/bin/env python3
"""Sharded, fingerprinted and attested execution of the complete ci/tests suite.

This module is control code for ``product-validation / workflow-source-checks``.
It deliberately lives under ``ci/tests/`` (and has no ``test`` prefix, so
``unittest discover`` never collects it): product phase selection ignores
``ci/tests/`` entirely, so this control cannot change any product inventory.

Three operations exist:

``run-shard``
    Discover the *complete* suite exactly like ``python3 -m unittest discover
    -s ci/tests`` (every module is imported in every shard, so import-time
    side effects are identical), then run one deterministic module partition.
``accept``
    Join every shard report, prove that the executed test IDs are pairwise
    disjoint and that their union is exactly the discovered suite, and write
    an unsigned record bound to the source-check fingerprint.  The workflow
    then signs the record with GitHub's native Sigstore attestation.
``discover-reuse``
    Accept a previously signed record only after authenticating it like other
    reused originals: an exact GitHub upload of an allowed successful original
    ``ci.yml`` attempt, the original job and upload window, the protected
    publisher reference and a native attestation whose source digest is the
    original tested commit.  The fingerprint is recomputed from authenticated
    identities, never taken from the record.  Any miss runs the suite.

The fingerprint covers the whole tested Git tree (tests read workflows,
actions, build logic, bindings and Git inventories of the entire checkout),
the executing protected workflow definition, the interpreter, the runner image,
Git, the pinned actionlint version and every ``CODEX_AGENT_*`` variable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "codex-agent-labs/codex-agent"
CALLER_WORKFLOW = ".github/workflows/ci.yml"
EXECUTOR_WORKFLOW = ".github/workflows/product-validation.yml"
PUBLISHER_REF = "refs/remotes/origin/reuse-authority"
JOB_NAME = "product-validation / workflow-source-checks"
SHARDS = 8
ACTIONLINT_VERSION = "1.7.12"
ARTIFACT_PREFIX = "codex-agent-source-checks-"
MAX_ATTEMPTS = 5
MAX_CANDIDATES = 8
UPLOAD_LIMIT = 4 * 1024 * 1024
RECORD = "source-checks.json"
BUNDLE = "bundle.jsonl"
WEIGHTS = Path(__file__).resolve().parent / "data" / "source-check-weights.json"
_OID = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


# --------------------------------------------------------------------------
# Canonical helpers (kept local so the shard runner imports nothing from ci/
# before discovery; ci/ modules are only imported by the reuse verifier).


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8") + b"\n"


def load_canonical(raw: bytes):
    value = json.loads(raw.decode("utf-8"))
    if canonical(value) != raw:
        raise ValueError("Source-check JSON is not canonical")
    return value


def sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f"{label} has unexpected fields")
    return value


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(["git", "--no-replace-objects", *arguments], cwd=root, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


def require_oid(value, label):
    if type(value) is not str or _OID.fullmatch(value) is None:
        raise ValueError(f"{label} must be an exact lowercase Git object ID")
    return value


# --------------------------------------------------------------------------
# Suite inventory and deterministic partitioning.


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


def discover(root: Path = ROOT) -> list[unittest.TestCase]:
    """Exactly the CI loader: ``unittest discover -s ci/tests`` from the root."""
    if Path.cwd().resolve() != root.resolve():
        raise ValueError("Source checks must run from the repository root")
    # ``python3 -m unittest`` starts with the working directory, then discovery
    # prepends the top-level ci/tests directory. Reproduce that exact order
    # instead of this script's own directory.
    start = str((root / "ci" / "tests").resolve())
    if sys.path and Path(sys.path[0] or ".").resolve() == Path(start):
        sys.path[0] = os.getcwd()
    elif not sys.path or sys.path[0] != os.getcwd():
        sys.path.insert(0, os.getcwd())
    loader = unittest.TestLoader()
    tests = list(_flatten(loader.discover("ci/tests")))
    if loader.errors:
        raise ValueError("Source-check discovery reported loader errors: " + "; ".join(loader.errors))
    if not tests:
        raise ValueError("Source-check discovery found no tests")
    return tests


def module_key(test: unittest.TestCase) -> str:
    # A module that fails to import still runs (and fails) in exactly one shard.
    if isinstance(test, unittest.loader._FailedTest):
        return test._testMethodName
    return type(test).__module__


def inventory(ids) -> dict:
    """Multiset identity: a class imported into two modules is collected (and
    must run) twice, exactly as ``unittest discover`` runs it."""
    ordered = sorted(ids)
    if any(type(value) is not str or not value or "\n" in value for value in ordered):
        raise ValueError("Source-check inventory contains a malformed test ID")
    return {"count": len(ordered), "sha256": sha256("".join(f"{value}\n" for value in ordered).encode())}


def load_weights(path: Path = WEIGHTS) -> dict[str, float]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict or any(type(key) is not str or type(weight) not in (int, float)
                                      or weight < 0 for key, weight in value.items()):
        raise ValueError("Source-check weights are malformed")
    return {key: float(weight) for key, weight in value.items()}


def partition(modules, shards: int, weights: dict[str, float]) -> list[list[str]]:
    """Deterministic longest-processing-time assignment of whole modules."""
    if type(shards) is not int or shards < 1:
        raise ValueError("Source-check shard count must be positive")
    names = sorted(set(modules))
    default = 1.0
    bins = [[0.0, index, []] for index in range(shards)]
    for name in sorted(names, key=lambda item: (-weights.get(item, default), item)):
        target = min(bins, key=lambda row: (row[0], row[1]))
        target[0] += weights.get(name, default)
        target[2].append(name)
    return [sorted(row[2]) for row in bins]


# --------------------------------------------------------------------------
# Fingerprint inputs.


def environment(environ=None) -> dict:
    environ = os.environ if environ is None else environ
    variables = sorted([name, sha256(value.encode("utf-8"))] for name, value in environ.items()
                       if name.startswith("CODEX_AGENT_"))
    return {
        "python": sys.version,
        "implementation": sys.implementation.name,
        "system": platform.system(),
        "machine": platform.machine(),
        # The hosted image build (ImageVersion) is deliberately excluded: GitHub
        # serves several builds of one image to parallel shards, while every tool
        # the suite executes is bound by its own version below.
        "imageOS": environ.get("ImageOS"),
        "runnerEnvironment": environ.get("RUNNER_ENVIRONMENT"),
        "git": subprocess.run(["git", "--version"], check=True, stdout=subprocess.PIPE,
                              text=True).stdout.strip(),
        "actionlint": ACTIONLINT_VERSION,
        "variables": variables,
    }


def clean_checkout(root: Path) -> tuple[str, str]:
    commit = require_oid(git(root, "rev-parse", "HEAD^{commit}"), "Source-check commit")
    tree = require_oid(git(root, "rev-parse", "HEAD^{tree}"), "Source-check tree")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"):
        raise ValueError("Source checks require a clean checkout of the exact tested tree")
    return commit, tree


def executor_blob(root: Path, publisher_sha: str) -> str:
    """The executing protected workflow definition, bound by its Git blob."""
    require_oid(publisher_sha, "Protected publisher")
    if git(root, "rev-parse", f"{publisher_sha}^{{commit}}") != publisher_sha:
        raise ValueError("Protected publisher is not an exact commit")
    # Only a commit reachable from the protected publisher branch is admitted.
    subprocess.run(["git", "--no-replace-objects", "merge-base", "--is-ancestor", publisher_sha,
                    PUBLISHER_REF], cwd=root, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    return require_oid(git(root, "rev-parse", f"{publisher_sha}:{EXECUTOR_WORKFLOW}"),
                       "Protected executor workflow blob")


def inputs(*, tree: str, blob: str, env: dict, suite: dict) -> dict:
    return {"schemaVersion": 1, "tree": require_oid(tree, "Tested tree"),
            "executor": {"path": EXECUTOR_WORKFLOW, "blob": require_oid(blob, "Executor blob")},
            "environment": env, "suite": exact(suite, {"count", "sha256"}, "Suite inventory")}


def fingerprint(value: dict) -> str:
    return sha256(canonical(value))


def artifact_name(value: str, attempt: int) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError("Source-check fingerprint is malformed")
    return f"{ARTIFACT_PREFIX}{value[7:]}-attempt-{attempt}"


# --------------------------------------------------------------------------
# Shard execution.


class _RecordingResult(unittest.TextTestResult):
    def __init__(self, *arguments, **keywords):
        super().__init__(*arguments, **keywords)
        self.started: list[str] = []
        self.fixture_skips: set[str] = set()
        self.module_seconds: dict[str, float] = {}
        self._clock = None

    def startTest(self, test):
        self.started.append(test.id())
        self._clock = module_key(test), time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        if self._clock is not None:
            name, began = self._clock
            self.module_seconds[name] = self.module_seconds.get(name, 0.0) + time.monotonic() - began
            self._clock = None

    def addSkip(self, test, reason):
        # A skipped setUpClass/setUpModule reports once and runs no member test.
        if isinstance(test, unittest.suite._ErrorHolder):
            self.fixture_skips.add(test.description)
        super().addSkip(test, reason)


def _fixture_skipped(test, skips: set[str]) -> bool:
    cls = type(test)
    return (f"setUpClass ({cls.__module__}.{cls.__qualname__})" in skips
            or f"setUpModule ({cls.__module__})" in skips)


def run_actionlint(executable: str, root: Path) -> dict:
    version = subprocess.run([executable, "-version"], cwd=root, check=True, stdout=subprocess.PIPE,
                             text=True).stdout
    if version.splitlines()[0].strip() not in {ACTIONLINT_VERSION, "v" + ACTIONLINT_VERSION}:
        raise ValueError("actionlint is not the pinned source-check version")
    result = subprocess.run([executable], cwd=root)
    return {"version": ACTIONLINT_VERSION, "passed": result.returncode == 0}


def run_shard(shard: int, shards: int, report: Path, *, actionlint: str | None, root: Path = ROOT) -> bool:
    if not 0 <= shard < shards:
        raise ValueError("Source-check shard index is outside the shard count")
    commit, tree = clean_checkout(root)
    env = environment()
    lint = run_actionlint(actionlint, root) if actionlint is not None else None
    tests = discover(root)
    suite = inventory(test.id() for test in tests)
    assigned_modules = set(partition((module_key(test) for test in tests), shards, load_weights())[shard])
    selected = [test for test in tests if module_key(test) in assigned_modules]
    started = time.monotonic()
    # Same runner policy as ``python3 -m unittest -v`` (default warning filter).
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2, resultclass=_RecordingResult,
                                     warnings=None if sys.warnoptions else "default").run(
        unittest.TestSuite(selected))
    elapsed = time.monotonic() - started
    started_ids = list(result.started)
    remaining = {}
    for value in started_ids:
        remaining[value] = remaining.get(value, 0) + 1
    executed = list(started_ids)
    for test in selected:
        if remaining.get(test.id(), 0):
            remaining[test.id()] -= 1
        elif _fixture_skipped(test, result.fixture_skips):
            executed.append(test.id())
    executed.sort()
    assigned = inventory(test.id() for test in selected)
    passed = (result.wasSuccessful() and inventory(executed) == assigned
              and (lint is None or lint["passed"]))
    value = {
        "schemaVersion": 1, "kind": "codex-agent-source-check-shard",
        "shard": shard, "shards": shards, "commit": commit, "tree": tree,
        "environment": env, "suite": suite, "assigned": assigned, "executed": executed,
        "actionlint": lint, "elapsedSeconds": round(elapsed, 3),
        # Diagnostics only: regenerate data/source-check-weights.json to rebalance.
        "moduleSeconds": {name: round(value, 3) for name, value in sorted(result.module_seconds.items())},
        "result": {"testsRun": result.testsRun, "failures": len(result.failures),
                   "errors": len(result.errors), "skipped": len(result.skipped),
                   "expectedFailures": len(result.expectedFailures),
                   "unexpectedSuccesses": len(result.unexpectedSuccesses), "passed": passed},
    }
    if (git(root, "rev-parse", "HEAD^{commit}"), git(root, "rev-parse", "HEAD^{tree}")) != (commit, tree):
        raise ValueError("Source-check checkout changed during the shard")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_bytes(canonical(value))
    return passed


# --------------------------------------------------------------------------
# Joining shard reports into a record.

_SHARD_KEYS = {"schemaVersion", "kind", "shard", "shards", "commit", "tree", "environment", "suite",
               "assigned", "executed", "actionlint", "elapsedSeconds", "moduleSeconds", "result"}


_SHARD_UPLOAD = re.compile(r"codex-agent-source-check-shard-([0-9]+)-attempt-([1-9][0-9]*)")


def latest_reports(directory: Path, shards: int, attempt: int | None = None) -> list[Path]:
    """One report per shard: its newest attempt not after the current attempt.

    A re-run of failed jobs keeps earlier successful shard uploads; a full
    re-run supersedes them. Unexpected entries fail closed.
    """
    attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")) if attempt is None else attempt
    selected: dict[int, tuple[int, Path]] = {}
    for entry in sorted(Path(directory).iterdir()):
        match = _SHARD_UPLOAD.fullmatch(entry.name)
        if match is None or not entry.is_dir() or entry.is_symlink():
            raise ValueError(f"Unexpected source-check shard upload: {entry.name}")
        shard, upload_attempt = int(match[1]), int(match[2])
        members = sorted(entry.iterdir())
        if (not 0 <= shard < shards or upload_attempt > attempt
                or [member.name for member in members] != [f"shard-{shard}.json"]
                or not members[0].is_file() or members[0].is_symlink()):
            raise ValueError(f"Source-check shard upload is malformed: {entry.name}")
        if shard not in selected or selected[shard][0] < upload_attempt:
            selected[shard] = upload_attempt, members[0]
    if sorted(selected) != list(range(shards)):
        raise ValueError("Source-check shard reports are missing")
    return [selected[shard][1] for shard in range(shards)]


def join_reports(directory: Path, shards: int, *, commit: str, tree: str) -> tuple[dict, dict | None]:
    """Return (suite, environment) only for a complete, disjoint, passing union.

    The environment is None when shards ran on different runner images: the
    pass still counts, but it is not a single fingerprint and is never published.
    """
    reports = [exact(load_canonical(path.read_bytes()), _SHARD_KEYS, "Source-check shard report")
               for path in latest_reports(directory, shards)]
    if sorted(report["shard"] for report in reports) != list(range(shards)):
        raise ValueError("Source-check shard reports are missing or duplicated")
    first = reports[0]
    executed: list[str] = []
    for report in reports:
        if (report["schemaVersion"] != 1 or report["kind"] != "codex-agent-source-check-shard"
                or report["shards"] != shards or report["commit"] != commit or report["tree"] != tree
                or report["suite"] != first["suite"]):
            raise ValueError("Source-check shard reports disagree on their tested identity")
        if report["result"]["passed"] is not True or inventory(report["executed"]) != report["assigned"]:
            raise ValueError(f"Source-check shard {report['shard']} did not pass completely")
        expected_lint = report["shard"] == 0
        if expected_lint != (report["actionlint"] is not None) or expected_lint and report["actionlint"] != {
                "version": ACTIONLINT_VERSION, "passed": True}:
            raise ValueError("actionlint must pass exactly once with the pinned version")
        executed.extend(report["executed"])
    # Multiset equality: every discovered occurrence ran in exactly one shard.
    if inventory(executed) != first["suite"]:
        raise ValueError("Source-check shards do not cover the discovered suite exactly once")
    if first["suite"]["count"] < 1:
        raise ValueError("Source-check suite is empty")
    uniform = all(report["environment"] == first["environment"] for report in reports)
    return first["suite"], first["environment"] if uniform else None


def producer_from_environment(environ, *, commit: str, tree: str) -> dict:
    event = environ["GITHUB_EVENT_NAME"]
    if (environ.get("GITHUB_REPOSITORY") != REPOSITORY or environ.get("GITHUB_SHA") != commit
            or not environ.get("GITHUB_WORKFLOW_REF", "").startswith(f"{REPOSITORY}/{CALLER_WORKFLOW}@")
            or event not in {"pull_request", "merge_group"}):
        raise ValueError("Only an original same-repository ci.yml PR or merge-group run produces records")
    pull_request = None
    if event == "pull_request":
        payload = json.loads(Path(environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        pull_request = payload["pull_request"]["number"]
        if type(pull_request) is not int or pull_request < 1:
            raise ValueError("Pull-request record lacks its exact number")
    return {"repository": REPOSITORY, "workflowPath": CALLER_WORKFLOW, "commit": commit, "tree": tree,
            "event": event, "runId": int(environ["GITHUB_RUN_ID"]),
            "runAttempt": int(environ["GITHUB_RUN_ATTEMPT"]), "pullRequest": pull_request}


def accept(directory: Path, shards: int, *, publisher_sha: str | None, record: Path | None,
           environ=None, root: Path = ROOT) -> dict:
    """Fail unless the complete suite passed; optionally write a signable record."""
    environ = os.environ if environ is None else environ
    commit, tree = clean_checkout(root)
    suite, env = join_reports(directory, shards, commit=commit, tree=tree)
    result = {"suite": suite}
    if record is not None and env is not None:
        value_inputs = inputs(tree=tree, blob=executor_blob(root, publisher_sha), env=env, suite=suite)
        value = {"schemaVersion": 1, "kind": "codex-agent-source-checks", "result": "passed",
                 "fingerprint": fingerprint(value_inputs), "inputs": value_inputs,
                 "publisherSha": publisher_sha,
                 "producer": producer_from_environment(environ, commit=commit, tree=tree)}
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_bytes(canonical(value))
        result["record"] = value
    return result


# --------------------------------------------------------------------------
# Authenticated reuse.

_RECORD_KEYS = {"schemaVersion", "kind", "result", "fingerprint", "inputs", "publisherSha", "producer"}


def current_inputs(root: Path, publisher_sha: str) -> dict:
    _, tree = clean_checkout(root)
    return inputs(tree=tree, blob=executor_blob(root, publisher_sha), env=environment(),
                  suite=inventory(test.id() for test in discover(root)))


def verify_native_attestation(raw: bytes, bundle: bytes, *, publisher_sha: str, producer: dict) -> None:
    with tempfile.TemporaryDirectory(prefix="source-check-attestation-") as temporary:
        subject, signed = Path(temporary) / RECORD, Path(temporary) / BUNDLE
        subject.write_bytes(raw)
        signed.write_bytes(bundle)
        result = subprocess.run([
            "gh", "attestation", "verify", str(subject), "--bundle", str(signed),
            "--repo", REPOSITORY, "--signer-workflow", f"{REPOSITORY}/{EXECUTOR_WORKFLOW}",
            "--signer-digest", publisher_sha, "--source-digest", producer["commit"],
            "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
            "--deny-self-hosted-runners", "--format", "json",
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        verified = json.loads(result.stdout)
        if subject.read_bytes() != raw or signed.read_bytes() != bundle:
            raise ValueError("Source-check record changed during native verification")
    expected = (f"https://github.com/{REPOSITORY}/actions/runs/{producer['runId']}"
                f"/attempts/{producer['runAttempt']}")
    if not isinstance(verified, list) or len(verified) < 1:
        raise ValueError("Native source-check attestation returned no verified statement")
    for row in verified:
        certificate = (((row or {}).get("verificationResult") or {}).get("signature") or {}).get("certificate")
        if not isinstance(certificate, dict) or certificate.get("runInvocationURI") != expected:
            raise ValueError("Native source-check attestation is not bound to its original attempt")


def authenticate(candidate: dict, current: dict, token: str, *, root: Path) -> dict:
    """Admit one listed upload only through the existing original-CI gates."""
    sys.path.insert(0, str(root / "ci"))
    import product_reuse as products
    from products.inventory import verified_zip_contents
    from products.receipt import validate_producer

    identifier = candidate.get("id")
    digest = candidate.get("digest")
    if type(identifier) is not int or identifier < 1 or type(digest) is not str or _SHA256.fullmatch(digest) is None:
        raise ValueError("Listed source-check upload identity is malformed")
    detail = products.api_json(f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{identifier}", token)
    if any(detail.get(field) != candidate.get(field) for field in ("id", "name", "digest", "workflow_run")):
        raise ValueError("Source-check upload changed after listing")
    size = detail.get("size_in_bytes")
    if type(size) is not int or not 0 < size <= UPLOAD_LIMIT:
        raise ValueError("Source-check upload exceeds its small transport bound")
    raw_zip = products.download_artifact(detail, token)
    with tempfile.TemporaryDirectory(prefix="source-check-reuse-") as temporary:
        archive = Path(temporary) / "upload.zip"
        archive.write_bytes(raw_zip)
        listed, contents, _ = verified_zip_contents(
            archive, max_archive_bytes=UPLOAD_LIMIT, max_members=2, max_entry_bytes=UPLOAD_LIMIT,
            max_total_bytes=UPLOAD_LIMIT, retained_paths=(RECORD, BUNDLE), max_retained_bytes=UPLOAD_LIMIT,
            require_sorted=False)
    if sorted(row["relativePath"] for row in listed) != sorted((BUNDLE, RECORD)):
        raise ValueError("Source-check upload must contain exactly its record and native bundle")
    raw, bundle = contents[RECORD], contents[BUNDLE]
    record = exact(load_canonical(raw), _RECORD_KEYS, "Source-check record")
    producer = validate_producer(record["producer"], "Source-check producer")
    publisher_sha = require_oid(record["publisherSha"], "Source-check publisher")
    if (record["schemaVersion"] != 1 or record["kind"] != "codex-agent-source-checks"
            or record["result"] != "passed" or record["inputs"] != current
            or record["fingerprint"] != fingerprint(current)
            or producer["repository"] != REPOSITORY or producer["workflowPath"] != CALLER_WORKFLOW
            or producer["event"] not in {"pull_request", "merge_group"}
            or producer["tree"] != current["tree"]):
        raise ValueError("Source-check record does not attest the current fingerprint")
    name = artifact_name(record["fingerprint"], producer["runAttempt"])
    if detail.get("name") != name:
        raise ValueError("Source-check upload name differs from its record attempt")
    # The protected publisher must be a real reuse-authority commit whose
    # executor definition is the one in the current fingerprint.
    if executor_blob(root, publisher_sha) != current["executor"]["blob"]:
        raise ValueError("Source-check publisher executes a different workflow definition")
    with products.verification_session(), products._ci_observation_batch(
            (str(producer["runId"]), str(producer["runAttempt"])), share_nested=True):
        observation, = products._observe_ci_producer_jobs(
            {"sources": producer}, jobs_by_phase={"sources": JOB_NAME}, token=token,
            trusted_workflows_by_phase={"sources": {"path": EXECUTOR_WORKFLOW, "sha": publisher_sha}})
        artifact = products._contract_ci_upload_metadata(identifier, digest, name, producer,
                                                         observation["run"], token)
        products._require_artifact_job_window(observation, JOB_NAME, artifact)
    verify_native_attestation(raw, bundle, publisher_sha=publisher_sha, producer=producer)
    return {"sourceRunId": producer["runId"], "sourceRunAttempt": producer["runAttempt"],
            "artifactId": identifier, "artifactSha256": digest, "recordSha256": sha256(raw)}


def discover_reuse(publisher_sha: str, token: str, *, root: Path = ROOT) -> dict:
    current = current_inputs(root, publisher_sha)
    value = fingerprint(current)
    result = {"reused": False, "fingerprint": value, "reason": "no-attested-record"}
    if not token:
        return {**result, "reason": "github-token-unavailable"}
    sys.path.insert(0, str(root / "ci"))
    import product_reuse as products
    from urllib.parse import urlencode

    candidates = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        name = artifact_name(value, attempt)
        listed = products.paginated_items(
            f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts?{urlencode({'name': name})}",
            "artifacts", token)
        candidates.extend(item for item in listed if type(item) is dict and item.get("name") == name
                          and item.get("expired") is False)
    candidates.sort(key=lambda item: (str(item.get("created_at")), item.get("id") or 0), reverse=True)
    failures = []
    for candidate in candidates[:MAX_CANDIDATES]:
        try:
            admitted = authenticate(candidate, current, token, root=root)
        except (KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
            failures.append(f"{candidate.get('id')}:{type(error).__name__}:{error}"[:300])
            continue
        if git(root, "rev-parse", "HEAD^{tree}") != current["tree"]:
            raise ValueError("Source-check checkout changed during reuse authentication")
        return {"reused": True, "fingerprint": value, "reason": "attested-record", **admitted}
    if failures:
        result["reason"] = "no-authenticated-record"
        result["failures"] = failures
    return result


# --------------------------------------------------------------------------


def _github_output(path, values: dict) -> None:
    if path is None:
        return
    names = {"sourceRunId": "source_run_id", "sourceRunAttempt": "source_run_attempt",
             "artifactId": "artifact_id", "artifactSha256": "artifact_sha256",
             "recordSha256": "record_sha256"}
    with open(path, "a", encoding="utf-8") as output:
        for key, item in values.items():
            if key == "failures":
                continue
            text = str(item).lower() if isinstance(item, bool) else str(item)
            if "\n" in text or "\r" in text:
                raise ValueError("Source-check output value is not a single line")
            output.write(f"{names.get(key, key)}={text}\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0], allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    shard = commands.add_parser("run-shard")
    shard.add_argument("--shard", type=int, required=True)
    shard.add_argument("--shards", type=int, default=SHARDS)
    shard.add_argument("--report", type=Path, required=True)
    shard.add_argument("--actionlint")
    join = commands.add_parser("accept")
    join.add_argument("--reports", type=Path, required=True)
    join.add_argument("--shards", type=int, default=SHARDS)
    join.add_argument("--publisher-sha")
    join.add_argument("--record", type=Path)
    join.add_argument("--github-output")
    reuse = commands.add_parser("discover-reuse")
    reuse.add_argument("--publisher-sha", required=True)
    reuse.add_argument("--github-output")
    listing = commands.add_parser("list")
    listing.add_argument("--shards", type=int, default=SHARDS)
    printed = commands.add_parser("fingerprint")
    printed.add_argument("--publisher-sha", required=True)
    arguments = parser.parse_args(argv)
    if arguments.command == "fingerprint":
        value = current_inputs(ROOT, arguments.publisher_sha)
        sys.stdout.buffer.write(canonical({"fingerprint": fingerprint(value), "inputs": value}))
        return 0
    if arguments.command == "run-shard":
        if arguments.shards != SHARDS:
            raise SystemExit("Source checks require the pinned shard count")
        return 0 if run_shard(arguments.shard, arguments.shards, arguments.report,
                              actionlint=arguments.actionlint) else 1
    if arguments.command == "accept":
        if arguments.shards != SHARDS:
            raise SystemExit("Source checks require the pinned shard count")
        if (arguments.publisher_sha is None) != (arguments.record is None):
            raise SystemExit("A published record requires its protected publisher")
        value = accept(arguments.reports, arguments.shards, publisher_sha=arguments.publisher_sha,
                       record=arguments.record)
        outputs = {"suite_count": value["suite"]["count"], "record": "record" in value}
        if "record" in value:
            record = value["record"]
            outputs.update(fingerprint=record["fingerprint"],
                           artifact_name=artifact_name(record["fingerprint"], record["producer"]["runAttempt"]))
        _github_output(arguments.github_output, outputs)
        print(json.dumps({key: str(item) for key, item in outputs.items()}))
        return 0
    if arguments.command == "discover-reuse":
        try:
            value = discover_reuse(arguments.publisher_sha, os.environ.get("GITHUB_TOKEN", ""))
        except (KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
            # Discovery is only an optimisation: any failure runs the suite.
            value = {"reused": False, "fingerprint": "", "reason": f"discovery-unavailable:{type(error).__name__}"}
        _github_output(arguments.github_output, value)
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    tests = discover(ROOT)
    parts = partition((module_key(test) for test in tests), arguments.shards, load_weights())
    weights = load_weights()
    for index, modules in enumerate(parts):
        count = sum(1 for test in tests if module_key(test) in set(modules))
        print(index, len(modules), count, round(sum(weights.get(name, 1.0) for name in modules), 1))
    print(json.dumps(inventory(test.id() for test in tests)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
