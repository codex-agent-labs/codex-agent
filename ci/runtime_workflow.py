"""Thin workflow composition over the existing authenticated product planner."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import product_reuse as products
from products.inventory import canonical_json_bytes, snapshot_regular_tree
from products.registry import PhaseInstanceId
from reuse import github_output


def matrix(plan_path, discovery_root, state_root, github_output_path, *, repository_root=None, environ=None):
    value = products.runtime_worker_matrix(
        plan_path, discovery_root, state_root, repository_root=repository_root, environ=environ)
    supervisors = [row["buildKey"] for row in value["include"]
                   if products._identity(row) == PhaseInstanceId("runtime", "linux-arm64", "binary", "linux-arm64")]
    if len(supervisors) > 1:
        raise ValueError("Duplicate elected Runtime supervisor")
    github_output(github_output_path, {
        "runtime_matrix": canonical_json_bytes(value).decode().strip(),
        "runtime_workers_required": bool(value["include"]),
        "supervisor_key": supervisors[0] if supervisors else "",
    })
    return value


def capture(plan_path, destination, github_output_path, *, artifact_id, artifact_sha256,
            trusted_workflow_sha, state_wave=0, instance=None, expected_build_key=None,
            repository_root=None, environ=None, token):
    products.capture_runtime_resume_upload(
        plan_path, destination, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
        trusted_workflow_sha=trusted_workflow_sha, state_wave=state_wave,
        repository_root=repository_root, environ=environ, token=token)
    original = destination / "original"
    paths = {
        "input_root": original,
        "plan_path": original / "product-resume-inputs/plan/impact-plan.json",
        "discovery_root": original / "product-resume-state",
        "state_root": original / ("runtime-state" if state_wave else "product-resume-state"),
    }
    value = matrix(paths["plan_path"], paths["discovery_root"], paths["state_root"], github_output_path,
                   repository_root=repository_root, environ=environ)
    if (instance is None) != (expected_build_key is None):
        raise ValueError("Runtime worker identity and elected key must be supplied together")
    if instance is not None:
        rows = [row for row in value["include"] if products._identity(row) == instance]
        if len(rows) != 1 or rows[0]["buildKey"] != expected_build_key:
            raise ValueError("Runtime workflow worker is not elected with the exact requested key")
        paths["phase_plan"] = paths["state_root"] / "phase-plans" / (
            f"runtime-{instance.component}-{instance.phase}-{instance.target}.json")
    github_output(github_output_path, {name: str(path) for name, path in paths.items()})
    return {**paths, "matrix": value}


def collect(input_root, destination, github_output_path, *, wave, trusted_workflow_sha,
            repository_root=None, environ=None, token):
    if type(wave) is not int or not 1 <= wave <= 4:
        raise ValueError("Runtime workflow wave must be one through four")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    input_root, _, destination = products._product_materialization_paths(root, input_root, input_root, destination)
    plan = input_root / "product-resume-inputs/plan/impact-plan.json"
    discovery = input_root / "product-resume-state"
    state = input_root / ("runtime-state" if wave > 1 else "product-resume-state")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime workflow destination must not exist")
    collection = products.collect_runtime_workers(
        plan, discovery, state, destination / "collection", trusted_workflow_sha=trusted_workflow_sha,
        repository_root=repository_root, environ=environ, token=token)
    shards = [destination / "collection" / row["shardDirectory"]
              for row in collection["rows"] if row["result"] == "success"]
    failures = tuple(products._identity(row) for row in collection["rows"] if row["result"] != "success")
    handoff = destination / "handoff"
    advanced = products.advance_products(
        plan, discovery, state, shards, handoff / "runtime-state", github_output_path,
        repository_root=repository_root, environ=environ, failed_instances=failures, runtime_workers_only=True)
    # Original input and receipt bytes are forwarded, not regenerated. Collection
    # diagnostics have their own upload, avoiding recursively nested wave archives.
    for name in ("product-resume-inputs", "product-resume-state"):
        snapshot_regular_tree(input_root / name, handoff / name, allow_empty=True)
    if failures:
        github_output(github_output_path, {"runtime_matrix": '{"include":[]}',
                                          "runtime_workers_required": False, "supervisor_key": ""})
    else:
        next_matrix = matrix(handoff / "product-resume-inputs/plan/impact-plan.json",
                             handoff / "product-resume-state", handoff / "runtime-state", github_output_path,
                             repository_root=repository_root, environ=environ)
        if wave == 4 and next_matrix["include"]:
            raise ValueError("Runtime workers remain after four dependency-ordered waves")
    return advanced


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("matrix")
    for name in ("plan", "discovery-root", "state-root", "github-output"):
        show.add_argument(f"--{name}", type=Path, required=True)
    captured = commands.add_parser("capture")
    for name in ("plan", "destination", "github-output"):
        captured.add_argument(f"--{name}", type=Path, required=True)
    captured.add_argument("--artifact-id", type=int, required=True)
    captured.add_argument("--artifact-sha256", required=True)
    captured.add_argument("--trusted-workflow-sha", required=True)
    captured.add_argument("--state-wave", type=int, default=0)
    for name in ("component", "phase", "target", "expected-build-key"):
        captured.add_argument(f"--{name}")
    collected = commands.add_parser("collect")
    for name in ("input-root", "destination", "github-output"):
        collected.add_argument(f"--{name}", type=Path, required=True)
    collected.add_argument("--wave", type=int, required=True)
    collected.add_argument("--trusted-workflow-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "matrix":
            matrix(args.plan, args.discovery_root, args.state_root, args.github_output)
        elif args.command == "capture":
            values = (args.component, args.phase, args.target, args.expected_build_key)
            if any(value is not None for value in values) and any(value is None for value in values):
                raise ValueError("All four elected worker arguments are required")
            capture(args.plan, Path(os.path.abspath(args.destination)), args.github_output,
                    artifact_id=args.artifact_id, artifact_sha256=args.artifact_sha256,
                    trusted_workflow_sha=args.trusted_workflow_sha, state_wave=args.state_wave,
                    instance=PhaseInstanceId("runtime", *values[:3]) if all(values) else None,
                    expected_build_key=args.expected_build_key, token=os.environ.get("GITHUB_TOKEN", ""))
        else:
            collect(Path(os.path.abspath(args.input_root)), Path(os.path.abspath(args.destination)), args.github_output,
                    wave=args.wave, trusted_workflow_sha=args.trusted_workflow_sha,
                    token=os.environ.get("GITHUB_TOKEN", ""))
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
