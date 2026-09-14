"""Thin workflow composition over the existing authenticated product planner."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import product_reuse as products
from products.inventory import canonical_json_bytes, require_sha256, snapshot_regular_tree
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from reuse import github_output


def matrix(plan_path, discovery_root, state_root, github_output_path, *, repository_root=None, environ=None,
           sdk_validation_tooling=None):
    value = products.runtime_worker_matrix(
        plan_path, discovery_root, state_root, repository_root=repository_root, environ=environ,
        **({"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}))
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


def continuation(plan_path, discovery_root, state_root, github_output_path, *,
                 repository_root=None, environ=None, sdk_validation_tooling=None,
                 require_completed=False, if_selected=False):
    """Route the final fully materialized Runtime closure, not early native fanout.

    The sole replay supplies every identity/key/receipt. A completed aggregate
    here is an unsigned payload state, never signature or CI signing authority.
    Protected callers must independently capture/elect these same originals.
    Empty standalone worker matrices do not establish this prerequisite.
    """
    if type(require_completed) is not bool or type(if_selected) is not bool:
        raise ValueError("Runtime continuation selection/completion requirements must be boolean")
    inspected = products.inspect_products(plan_path, discovery_root, state_root,
        repository_root=repository_root, environ=environ,
        sdk_validation_tooling=sdk_validation_tooling, include_sdk_selection=True)
    sdk = inspected.get("sdkInputSelection")
    sdk_outputs = {"sdk_handoff_required": sdk is not None,
                   "sdk_input_selection": canonical_json_bytes(sdk).decode().strip()}
    aggregate = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
    phases = {}
    for record in inspected["result"]["phases"]:
        instance = products._identity(record)
        if instance in phases:
            raise ValueError("Duplicate replayed Runtime continuation identity")
        phases[instance] = record
    ready = {}
    for plan in inspected["readyPlans"]:
        instance = products._identity(plan)
        if instance in ready:
            raise ValueError("Duplicate replayed Runtime continuation plan")
        ready[instance] = plan
    if aggregate not in phases:
        if not if_selected or require_completed or aggregate in ready:
            raise ValueError("Runtime continuation requires a selected aggregate")
        github_output(github_output_path, {
            **sdk_outputs,
            "native_attestation_matrix": '{"include":[]}', "aggregate_state": "not-selected",
            "aggregate_key": "", "aggregate_receipt_sha256": "",
            "aggregate_required": False, "aggregate_payload_complete": False,
        })
        return {"nativeAttestationMatrix": {"include": []},
                "aggregate": {"state": "not-selected", "buildKey": None, "receiptSha256": None}}
    closure = products._dependency_closure((aggregate,))
    for instance in closure:
        if instance == aggregate:
            continue
        record = phases.get(instance)
        if record is None or record["state"] not in {"retained", "reused"}:
            raise ValueError(f"Runtime continuation has an incomplete original predecessor: {instance}")
        for name in ("buildKey", "receiptSha256", "objectSha256"):
            require_sha256(record[name], f"Completed Runtime predecessor {name}")

    selected = phases[aggregate]
    key = require_sha256(selected["buildKey"], "Runtime aggregate elected key")
    if selected["state"] in {"retained", "reused"}:
        if aggregate in ready:
            raise ValueError("Completed Runtime aggregate also has a build election")
        receipt = require_sha256(selected["receiptSha256"], "Original Runtime aggregate receipt")
        require_sha256(selected["objectSha256"], "Original Runtime aggregate object")
        status = "completed"
    elif (selected["state"] == "build" and aggregate in ready
          and ready[aggregate]["buildKey"] == key
          and selected["receiptSha256"] is None and selected["objectSha256"] is None):
        receipt, status = None, "ready"
    else:
        raise ValueError("Runtime aggregate lacks an exact ready plan or completed original payload")
    if require_completed and status != "completed":
        raise ValueError("Runtime aggregate payload remains incomplete after collection")
    native = {"include": [{"target": target,
        "buildKey": phases[PhaseInstanceId("runtime", target, "metadata", target)]["buildKey"]}
        for target in NATIVE_TARGETS]}
    # Routing only: the protected caller still authenticates the complete
    # carrier and all selected originals, with no invalid-proof fallback.
    if status == "completed" and any(record["receiptSha256"] == receipt
            for record in inspected.get("runtimeAggregateReleaseEvidence", [])):
        native = {"include": []}
    value = {"nativeAttestationMatrix": native,
             "aggregate": {"state": status, "buildKey": key, "receiptSha256": receipt}}
    # Publish all routing fields together only after every prerequisite passes.
    github_output(github_output_path, {
        **sdk_outputs,
        "native_attestation_matrix": canonical_json_bytes(native).decode().strip(),
        "aggregate_state": status, "aggregate_key": key,
        "aggregate_receipt_sha256": receipt or "",
        "aggregate_required": status == "ready",
        "aggregate_payload_complete": status == "completed",
    })
    return value


def capture(plan_path, destination, github_output_path, *, artifact_id, artifact_sha256,
            trusted_workflow_sha, state_wave=0, instance=None, expected_build_key=None,
            repository_root=None, environ=None, token, sdk_validation_tooling=None):
    tooling = {"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}
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
                   repository_root=repository_root, environ=environ, **tooling)
    if (instance is None) != (expected_build_key is None):
        raise ValueError("Runtime worker identity and elected key must be supplied together")
    if instance is not None:
        if instance == PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"):
            selected = continuation(paths["plan_path"], paths["discovery_root"], paths["state_root"],
                                    github_output_path, repository_root=repository_root, environ=environ, **tooling)["aggregate"]
            if selected["state"] != "ready" or selected["buildKey"] != expected_build_key:
                raise ValueError("Runtime aggregate is not elected with the exact requested key")
        else:
            rows = [row for row in value["include"] if products._identity(row) == instance]
            if len(rows) != 1 or rows[0]["buildKey"] != expected_build_key:
                raise ValueError("Runtime workflow worker is not elected with the exact requested key")
        paths["phase_plan"] = paths["state_root"] / "phase-plans" / (
            f"runtime-{instance.component}-{instance.phase}-{instance.target}.json")
    github_output(github_output_path, {name: str(path) for name, path in paths.items()})
    return {**paths, "matrix": value}


def collect(input_root, destination, github_output_path, *, wave, trusted_workflow_sha,
            repository_root=None, environ=None, token, state_wave=None):
    if type(wave) is not int or not 1 <= wave <= 5:
        raise ValueError("Runtime workflow wave must be one through five")
    # Aggregate may already be ready in initial reuse, before any native wave.
    # Keep fixed preceding-wave defaults for the existing four worker waves.
    state_wave = wave - 1 if state_wave is None else state_wave
    if (type(state_wave) is not int or not 0 <= state_wave <= 4
            or (wave < 5 and state_wave != wave - 1)):
        raise ValueError("Runtime collection has an invalid predecessor state wave")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    input_root, _, destination = products._product_materialization_paths(root, input_root, input_root, destination)
    plan = input_root / "product-resume-inputs/plan/impact-plan.json"
    discovery = input_root / "product-resume-state"
    state = input_root / ("runtime-state" if state_wave else "product-resume-state")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime workflow destination must not exist")
    collection = products.collect_runtime_workers(
        plan, discovery, state, destination / "collection", trusted_workflow_sha=trusted_workflow_sha,
        repository_root=repository_root, environ=environ, token=token,
        **({"runtime_aggregate_only": True} if wave == 5 else {}))
    if wave == 5 and (len(collection["rows"]) != 1 or products._identity(collection["rows"][0]) !=
                      PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")):
        raise ValueError("Runtime aggregate collection requires its sole elected aggregate row")
    shards = [destination / "collection" / row["shardDirectory"]
              for row in collection["rows"] if row["result"] == "success"]
    failures = tuple(products._identity(row) for row in collection["rows"] if row["result"] != "success")
    handoff = destination / "handoff"
    advanced = products.advance_products(
        plan, discovery, state, shards, handoff / "runtime-state", github_output_path,
        repository_root=repository_root, environ=environ, failed_instances=failures,
        **({"runtime_aggregate_only": True} if wave == 5 else {"runtime_workers_only": True}))
    # Original input and receipt bytes are forwarded, not regenerated. Collection
    # diagnostics have their own upload, avoiding recursively nested wave archives.
    for name in ("product-resume-inputs", "product-resume-state"):
        snapshot_regular_tree(input_root / name, handoff / name, allow_empty=True)
    if wave == 5:
        if failures:
            github_output(github_output_path, {
                "native_attestation_matrix": '{"include":[]}',
                "aggregate_state": "failed", "aggregate_key": "", "aggregate_receipt_sha256": "",
                "aggregate_required": False, "aggregate_payload_complete": False,
            })
        else:
            continuation(handoff / "product-resume-inputs/plan/impact-plan.json",
                         handoff / "product-resume-state", handoff / "runtime-state", github_output_path,
                         repository_root=repository_root, environ=environ, require_completed=True)
    elif failures:
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
    show.add_argument("--sdk-validation-tooling", type=Path)
    final = commands.add_parser("continuation")
    for name in ("plan", "discovery-root", "state-root", "github-output"):
        final.add_argument(f"--{name}", type=Path, required=True)
    final.add_argument("--sdk-validation-tooling", type=Path)
    final.add_argument("--if-selected", action="store_true")
    final.add_argument("--require-completed", action="store_true")
    captured = commands.add_parser("capture")
    for name in ("plan", "destination", "github-output"):
        captured.add_argument(f"--{name}", type=Path, required=True)
    captured.add_argument("--artifact-id", type=int, required=True)
    captured.add_argument("--artifact-sha256", required=True)
    captured.add_argument("--trusted-workflow-sha", required=True)
    captured.add_argument("--state-wave", type=int, default=0)
    captured.add_argument("--sdk-validation-tooling", type=Path)
    for name in ("component", "phase", "target", "expected-build-key"):
        captured.add_argument(f"--{name}")
    collected = commands.add_parser("collect")
    for name in ("input-root", "destination", "github-output"):
        collected.add_argument(f"--{name}", type=Path, required=True)
    collected.add_argument("--wave", type=int, required=True)
    collected.add_argument("--state-wave", type=int)
    collected.add_argument("--trusted-workflow-sha", required=True)
    trust = commands.add_parser("variant-trust")
    trust.add_argument("--variant-handoff", action="append", required=True, metavar="TARGET=PATH")
    for name in ("destination", "keyring", "keys-directory"):
        trust.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "matrix":
            tooling = ({} if args.sdk_validation_tooling is None else {"sdk_validation_tooling":
                products._canonical_control(args.sdk_validation_tooling, "Caller SDK tooling policy")})
            matrix(args.plan, args.discovery_root, args.state_root, args.github_output, **tooling)
        elif args.command == "continuation":
            tooling = (None if args.sdk_validation_tooling is None else
                       products._canonical_control(args.sdk_validation_tooling, "Caller SDK tooling policy"))
            continuation(args.plan, args.discovery_root, args.state_root, args.github_output,
                         sdk_validation_tooling=tooling, **({"if_selected": True} if args.if_selected else {}),
                         **({"require_completed": True} if args.require_completed else {}))
        elif args.command == "capture":
            tooling = ({} if args.sdk_validation_tooling is None else {"sdk_validation_tooling":
                products._canonical_control(args.sdk_validation_tooling, "Caller SDK tooling policy")})
            values = (args.component, args.phase, args.target, args.expected_build_key)
            if any(value is not None for value in values) and any(value is None for value in values):
                raise ValueError("All four elected worker arguments are required")
            capture(args.plan, Path(os.path.abspath(args.destination)), args.github_output,
                    artifact_id=args.artifact_id, artifact_sha256=args.artifact_sha256,
                    trusted_workflow_sha=args.trusted_workflow_sha, state_wave=args.state_wave,
                    instance=PhaseInstanceId("runtime", *values[:3]) if all(values) else None,
                    expected_build_key=args.expected_build_key, token=os.environ.get("GITHUB_TOKEN", ""), **tooling)
        elif args.command == "variant-trust":
            from products.runtime_variant_trust import stage_runtime_variant_trust
            handoffs = {}
            for value in args.variant_handoff:
                target, separator, path = value.partition("=")
                if not separator or target not in NATIVE_TARGETS or not path or target in handoffs:
                    raise ValueError("Variant handoffs require unique native TARGET=PATH entries")
                handoffs[target] = Path(path)
            stage_runtime_variant_trust(handoffs, args.destination,
                                        keyring=args.keyring, keys_directory=args.keys_directory)
        else:
            collect(Path(os.path.abspath(args.input_root)), Path(os.path.abspath(args.destination)), args.github_output,
                    wave=args.wave, trusted_workflow_sha=args.trusted_workflow_sha,
                    token=os.environ.get("GITHUB_TOKEN", ""),
                    **({"state_wave": args.state_wave} if args.state_wave is not None else {}))
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
