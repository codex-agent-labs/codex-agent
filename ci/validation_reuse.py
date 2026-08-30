#!/usr/bin/env python3
"""Reuse a successful PR aggregate when a merge group has the identical Git tree."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from impact import NATIVE_WRAPPER_LANES
from receipt import required_lanes, safe_extract
from reuse import download_artifact, paginated_items, run_matches_pr


BASE_FILES = {"impact-plan.json", "validation-receipt.json"}
M8_FILES = {
    "canonical-api.json",
    "canonical-coverage.json",
    "kotlin-parity.json",
    "java-parity.json",
    "javascript-typescript-parity.json",
    "swift-parity.json",
    "objective-c-parity.json",
    "c-abi-parity.json",
    "binding-obligations-m8.json",
}
M11_FILES = {
    "canonical-api.json",
    "canonical-coverage.json",
    "kotlin-parity.json",
    "java-parity.json",
    "javascript-typescript-parity.json",
    "swift-parity.json",
    "objective-c-parity.json",
    "c-abi-parity.json",
    "python-parity.json",
    "csharp-parity.json",
    "rust-parity.json",
    "cpp-parity.json",
    "dart-parity.json",
    "binding-obligations-m11.json",
}
NATIVE_WRAPPER_LANGUAGES = {"python", "csharp", "rust", "cpp", "dart"}


def exact_files(root: Path) -> set[str]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Reusable validation artifact root is unsafe")
    entries = list(root.iterdir())
    if any(not entry.is_file() or entry.is_symlink() for entry in entries):
        raise ValueError("Reusable validation artifact must contain only root regular files")
    actual = {entry.name for entry in entries}
    if actual not in (BASE_FILES, BASE_FILES | M8_FILES, BASE_FILES | M11_FILES):
        raise ValueError(
            f"Reusable validation file set mismatch: expected={sorted(BASE_FILES)} or "
            f"{sorted(BASE_FILES | M8_FILES)} or {sorted(BASE_FILES | M11_FILES)} "
            f"actual={sorted(actual)}"
        )
    return actual


def validate_native_wrapper_release(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Reusable native-wrapper release root is unsafe")
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != {"packages", "evidence", "sdks"} or any(
        not entry.is_dir() or entry.is_symlink() for entry in entries
    ):
        raise ValueError("Reusable native-wrapper release root is incomplete or unexpected")
    languages = list((root / "packages").iterdir())
    if {entry.name for entry in languages} != NATIVE_WRAPPER_LANGUAGES or any(
        not entry.is_dir() or entry.is_symlink() or not any(entry.iterdir()) for entry in languages
    ):
        raise ValueError("Reusable native-wrapper package language set is incomplete or unsafe")


def validate(root: Path, current_plan: Path) -> dict[str, object]:
    plan = json.loads(current_plan.read_text(encoding="utf-8"))
    files = exact_files(root)
    source_plan = json.loads((root / "impact-plan.json").read_text(encoding="utf-8"))
    receipt = json.loads((root / "validation-receipt.json").read_text(encoding="utf-8"))
    expected = {
        "schemaVersion", "repository", "event", "validationCommit", "validationTree",
        "impactPlan", "lanes", "result",
    }
    if set(receipt) != expected or receipt["schemaVersion"] != 1 or receipt["result"] != "passed":
        raise ValueError("Unsupported aggregate validation receipt")
    plan_keys = {
        "schemaVersion", "event", "repository", "pullRequest", "baseCommit", "headCommit",
        "validationCommit", "validationTree", "mergeReady", "androidEvidenceRequired", "full",
        "unknownPaths", "changedPaths", "lanes",
    }
    if set(source_plan) != plan_keys or source_plan.get("schemaVersion") != 1:
        raise ValueError("Reusable PR impact plan schema mismatch")
    if source_plan["lanes"].get("ios-swift-tests", {}).get("test") is True and files == BASE_FILES:
        raise ValueError("Reusable PR validation lacks required M8 binding evidence")
    native_wrappers_required = all(
        source_plan["lanes"].get(lane, {}).get("build") is True
        and source_plan["lanes"].get(lane, {}).get("test") is True
        for lane in NATIVE_WRAPPER_LANES
    )
    if native_wrappers_required and files != BASE_FILES | M11_FILES:
        raise ValueError("Reusable PR validation lacks required M11 native-wrapper evidence")
    if receipt["event"] != "pull_request" or source_plan.get("event") != "pull_request":
        raise ValueError("Only authoritative PR validation may satisfy an identical merge group")
    if (
        not source_plan.get("mergeReady")
        or receipt["repository"] != plan["repository"]
        or source_plan["repository"] != plan["repository"]
        or source_plan["pullRequest"] != plan.get("pullRequest")
    ):
        raise ValueError("Reusable PR validation identity mismatch")
    if (
        receipt["validationCommit"] != source_plan["validationCommit"]
        or receipt["validationTree"] != plan["validationTree"]
        or source_plan.get("validationTree") != plan["validationTree"]
    ):
        raise ValueError("Reusable PR validation tree mismatch")
    lanes = receipt["lanes"]
    if not isinstance(lanes, dict) or any(
        not isinstance(value, dict)
        or set(value) != {"runId", "runAttempt", "artifactName", "validationCommit", "validationTree", "result"}
        or value["result"] != "passed"
        for value in lanes.values()
    ):
        raise ValueError("Reusable PR validation lane set is malformed")
    required = required_lanes(source_plan)
    if set(lanes) != set(required):
        raise ValueError("Reusable PR validation lane set does not match its impact plan")
    if plan.get("androidEvidenceRequired") and not source_plan["androidEvidenceRequired"]:
        raise ValueError("Reusable PR validation lacks required Android evidence")
    for lane, state in plan.get("lanes", {}).items():
        if any(state.get(action) and not source_plan["lanes"].get(lane, {}).get(action) for action in ("build", "test", "metadata")):
            raise ValueError(f"Reusable PR validation does not cover merge-group work: {lane}")
    for lane, value in lanes.items():
        if (
            value["validationCommit"] != source_plan["validationCommit"]
            or value["validationTree"] != source_plan["validationTree"]
            or value["artifactName"] != f"codex-agent-ci-{lane}-{source_plan['validationTree']}"
        ):
            raise ValueError(f"Reusable PR lane provenance mismatch: {lane}")
    return receipt


def materialize(root: Path, current_plan: Path, output: Path) -> None:
    receipt = validate(root, current_plan)
    plan = json.loads(current_plan.read_text(encoding="utf-8"))
    receipt.update(
        event="merge_group",
        validationCommit=plan["validationCommit"],
        validationTree=plan["validationTree"],
        impactPlan=current_plan.name,
        lanes={lane: receipt["lanes"][lane] for lane in required_lanes(plan)},
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    files = exact_files(root)
    if files in (BASE_FILES | M8_FILES, BASE_FILES | M11_FILES):
        for name in files - BASE_FILES:
            shutil.copy2(root / name, output.parent / name)


def discover(plan_path: Path, destination: Path, token: str, api_url: str) -> dict[str, object]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    repository = plan["repository"]
    wanted = f"codex-agent-ci-validation-{plan['validationTree']}"
    candidate = destination.with_name(f"{destination.name}.candidate")
    native_destination = destination.with_name("reused-native-wrapper-release")
    native_candidate = native_destination.with_name(f"{native_destination.name}.candidate")
    try:
        runs = paginated_items(
            f"{api_url}/repos/{repository}/actions/workflows/ci.yml/runs?event=pull_request&status=completed",
            "workflow_runs",
            token,
        )
        for run in runs:
            if not isinstance(run, dict):
                raise ValueError("GitHub workflow run response is malformed")
            if run.get("conclusion") != "success" or not run_matches_pr(run, plan["pullRequest"]):
                continue
            artifacts = paginated_items(
                f"{api_url}/repos/{repository}/actions/runs/{run['id']}/artifacts",
                "artifacts",
                token,
            )
            if any(not isinstance(item, dict) for item in artifacts):
                raise ValueError("GitHub artifact response is malformed")
            artifact = next(
                (item for item in artifacts if item.get("name") == wanted and not item.get("expired")),
                None,
            )
            if artifact is None:
                continue
            try:
                archive_bytes = download_artifact(artifact, token)
                with tempfile.NamedTemporaryFile(suffix=".zip") as archive:
                    archive.write(archive_bytes)
                    archive.flush()
                    if candidate.exists():
                        shutil.rmtree(candidate)
                    safe_extract(Path(archive.name), candidate)
                validate(candidate, plan_path)
                if exact_files(candidate) == BASE_FILES | M11_FILES:
                    native_name = f"codex-agent-native-wrapper-packages-{plan['validationTree']}"
                    native_artifact = next(
                        (item for item in artifacts if item.get("name") == native_name and not item.get("expired")),
                        None,
                    )
                    if native_artifact is None:
                        continue
                    native_bytes = download_artifact(native_artifact, token)
                    with tempfile.NamedTemporaryFile(suffix=".zip") as archive:
                        archive.write(native_bytes)
                        archive.flush()
                        if native_candidate.exists():
                            shutil.rmtree(native_candidate)
                        safe_extract(Path(archive.name), native_candidate)
                    validate_native_wrapper_release(native_candidate)
                if destination.exists():
                    shutil.rmtree(destination)
                candidate.rename(destination)
                if native_candidate.exists():
                    if native_destination.exists():
                        shutil.rmtree(native_destination)
                    native_candidate.rename(native_destination)
                return {
                    "reused": True,
                    "sourceRunId": int(run["id"]),
                    "sourceRunAttempt": int(run.get("run_attempt", 1)),
                    "artifactName": wanted,
                }
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                if native_candidate.exists():
                    shutil.rmtree(native_candidate)
                continue
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    if candidate.exists():
        shutil.rmtree(candidate)
    if native_candidate.exists():
        shutil.rmtree(native_candidate)
    return {"reused": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("discover", "validate", "materialize"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.mode == "discover":
        result = discover(
            arguments.plan,
            arguments.destination,
            os.environ.get("GITHUB_TOKEN", ""),
            os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        )
    elif arguments.mode == "validate":
        validate(arguments.destination, arguments.plan)
        result = {"reused": True}
    else:
        if arguments.output is None:
            raise ValueError("Materialized validation receipt output is required")
        materialize(arguments.destination, arguments.plan, arguments.output)
        result = {"reused": True}
    if arguments.github_output:
        with arguments.github_output.open("a", encoding="utf-8") as output:
            for key, value in result.items():
                name = {"sourceRunId": "source_run_id", "sourceRunAttempt": "source_run_attempt", "artifactName": "artifact_name"}.get(key, key)
                output.write(f"{name}={str(value).lower() if isinstance(value, bool) else value}\n")


if __name__ == "__main__":
    main()
