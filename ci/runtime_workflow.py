"""Thin workflow composition over the existing authenticated product planner."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import product_reuse as products
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.inventory import canonical_json_bytes, load_json_bytes, require_sha256, snapshot_regular_tree
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from products.restore import verification_scoped
from reuse import github_output


def failed_ios_package(plan_path, selected, destination, *, trusted_workflow_sha, token,
                       repository_root=None, environ=None):
    """Record only a terminal failure; never authenticate or advance product state.

    The sole iOS package election cannot hide a successful sibling. Retries use
    ordinary collection so an earlier successful attempt is still recovered.
    """
    root = Path(repository_root or Path(__file__).resolve().parents[1]).resolve()
    plan = products._validate_plan(plan_path, root)
    producer = products._consumer(plan, os.environ if environ is None else environ)["producer"]
    if plan["remoteBuildAuthorized"] is not True or plan["event"] != "pull_request":
        raise ValueError("Early package failure requires an authorized PR plan")
    instance = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
    rows = selected.get("include") if type(selected) is dict else None
    if (type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict
            or products._identity(rows[0]) != instance):
        raise ValueError("Early package failure requires its sole original election")
    key = require_sha256(rows[0].get("buildKey"), "Original package election")
    if producer["runAttempt"] != 1:
        return False
    observed = products._observe_ci_producer_jobs({"resume": producer},
        jobs_by_phase={"resume": "product-validation / product-resume"},
        trusted_workflow_sha=trusted_workflow_sha, token=token)
    jobs = products._matching_ci_jobs(observed[0]["jobs"], products._worker_job_name("sdk", instance),
                                      expected_build_key=key)
    if len(jobs) != 1:
        raise ValueError("Original package worker is missing or ambiguous")
    job = jobs[0]
    products.require_integer(job.get("id"), "Original package job", 1)
    if (job.get("run_id") != producer["runId"] or job.get("head_sha") != observed[0]["run"]["head_sha"]
            or job.get("status") != "completed"):
        raise ValueError("Original package worker is not terminal for its exact producer")
    if job.get("conclusion") not in {"failure", "cancelled", "timed_out"}:
        return False
    name = (products._worker_artifact_prefix("sdk", instance)
            + f"{key[7:]}-{producer['tree']}-attempt-{producer['runAttempt']}")
    uploads = products.paginated_items(
        f"https://api.github.com/repos/{producer['repository']}/actions/runs/{producer['runId']}/artifacts",
        "artifacts", token)
    candidates = [item for item in uploads if isinstance(item, dict) and item.get("name") == name]
    if len(candidates) > 1:
        raise ValueError("Failed original package upload is ambiguous")
    artifact = None
    if candidates:
        candidate = candidates[0]
        artifact = products._contract_ci_upload_metadata(candidate.get("id"), candidate.get("digest"),
            name, producer, observed[0]["run"], token, upload_limit=products._IOS_PACKAGE_UPLOAD_LIMIT)
        products._require_artifact_job_window(observed[0], job["name"], artifact)
    report = {"schemaVersion": 1, "kind": "failed-worker-observation", "producer": producer,
        "result": "failure", "observed": observed, "worker": job, "artifact": artifact,
        "selected": rows[0], "admittedPhases": [], "productBodiesDownloaded": 0}
    products.write_canonical_json(destination, report)
    return True


def ios_validation_outcome(plan_path, selected, destination, *, trusted_workflow_sha, token,
                           repository_root=None, environ=None):
    """Route terminal worker outcomes, never grant phase or signing authority."""
    root = Path(repository_root or Path(__file__).resolve().parents[1]).resolve()
    plan = products._validate_plan(plan_path, root)
    producer = products._consumer(plan, os.environ if environ is None else environ)["producer"]
    if plan["remoteBuildAuthorized"] is not True:
        raise ValueError("Apple outcome requires an authorized original plan")
    rows = selected.get("include") if type(selected) is dict else None
    allowed = {PhaseInstanceId("sdk", "sdk-ios", "validation", target)
               for target in ("ios-arm64", "ios-simulator-arm64")}
    if (type(rows) is not list or not rows or any(type(row) is not dict for row in rows)
            or len({products._identity(row) for row in rows}) != len(rows)
            or any(products._identity(row) not in allowed for row in rows)):
        raise ValueError("Apple outcome requires its exact original target election")
    keys = {products._identity(row): require_sha256(row.get("buildKey"), "Apple outcome elected key")
            for row in rows}
    # An earlier successful attempt must still reach ordinary recovery.
    fallback = {"all_failed": False, "signing_required": True,
                "signing_matrix": canonical_json_bytes(selected).decode().strip()}
    if producer["runAttempt"] != 1 or plan["event"] != "pull_request":
        return fallback
    observed = products._observe_ci_producer_jobs({"resume": producer},
        jobs_by_phase={"resume": "product-validation / product-resume"},
        trusted_workflow_sha=trusted_workflow_sha, token=token)
    outcomes, successes, signing = [], [], []
    for instance in allowed - keys.keys():
        if any(job.get("conclusion") != "skipped" for job in products._matching_ci_jobs(
                observed[0]["jobs"], products._worker_job_name("sdk", instance))):
            raise ValueError("Apple outcome election omits an observed sibling")
    for row in rows:
        instance = products._identity(row)
        jobs = products._matching_ci_jobs(observed[0]["jobs"], products._worker_job_name("sdk", instance),
                                          expected_build_key=keys[instance])
        if len(jobs) != 1:
            raise ValueError("Apple outcome worker is missing or ambiguous")
        job = jobs[0]
        products.require_integer(job.get("id"), "Apple outcome job", 1)
        if (job.get("run_id") != producer["runId"] or job.get("head_sha") != observed[0]["run"]["head_sha"]
                or job.get("status") != "completed"):
            raise ValueError("Apple outcome worker is not terminal for its exact producer")
        if job.get("conclusion") == "success":
            successes.append(row)
        elif job.get("conclusion") not in {"failure", "cancelled", "timed_out"}:
            return fallback
        outcomes.append({"selected": row, "worker": job, "artifact": None})
    uploads = products.paginated_items(
        f"https://api.github.com/repos/{producer['repository']}/actions/runs/{producer['runId']}/artifacts",
        "artifacts", token)
    for outcome in outcomes:
        if outcome["worker"]["conclusion"] == "success":
            from sdk_apple_upload_locator import observe_retained_validation_attestation
            selected = outcome["selected"]
            retained = observe_retained_validation_attestation(selected["target"], selected["buildKey"],
                producer, token=token)
            if retained is None:
                signing.append(selected)  # Full capture/preparation precede new signing.
            else:
                outcome["retainedAttestation"] = retained
            continue
        instance = products._identity(outcome["selected"])
        name = (products._worker_artifact_prefix("sdk", instance)
                + f"{keys[instance][7:]}-{producer['tree']}-attempt-{producer['runAttempt']}")
        candidates = [item for item in uploads if isinstance(item, dict) and item.get("name") == name]
        if len(candidates) > 1:
            raise ValueError("Failed Apple worker upload is ambiguous")
        if candidates:
            artifact = products._contract_ci_upload_metadata(candidates[0].get("id"), candidates[0].get("digest"),
                name, producer, observed[0]["run"], token)
            products._require_artifact_job_window(observed[0], outcome["worker"]["name"], artifact)
            outcome["artifact"] = artifact
    products.write_canonical_json(destination, {"schemaVersion": 1, "kind": "worker-outcome-observation",
        "producer": producer, "observed": observed, "workers": outcomes,
        "admittedPhases": [], "productBodiesDownloaded": 0})
    return {"all_failed": not successes,
            "signing_required": bool(signing),
            "signing_matrix": canonical_json_bytes({"include": signing}).decode().strip()}


def matrix(plan_path, discovery_root, state_root, github_output_path, *, repository_root=None, environ=None,
           sdk_validation_tooling=None, sdk_apple_validation_policy=None, sdk_original_workflow_sha=None,
           sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, completed_frozen=None):
    value = products.runtime_worker_matrix(
        plan_path, discovery_root, state_root, repository_root=repository_root, environ=environ,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
        **({"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}),
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **({"sdk_original_workflow_sha": sdk_original_workflow_sha} if sdk_original_workflow_sha is not None else {}),
        **({"sdk_facade_metadata_admission": sdk_facade_metadata_admission} if sdk_facade_metadata_admission is not None else {}),
        **({"sdk_android_metadata_admission": sdk_android_metadata_admission} if sdk_android_metadata_admission is not None else {}))
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
                 require_completed=False, if_selected=False, sdk_apple_validation_policy=None,
                 sdk_original_workflow_sha=None,
                 sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, completed_frozen=None):
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
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
        sdk_validation_tooling=sdk_validation_tooling, include_sdk_selection=True,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **({"sdk_original_workflow_sha": sdk_original_workflow_sha} if sdk_original_workflow_sha is not None else {}),
        **({"sdk_facade_metadata_admission": sdk_facade_metadata_admission} if sdk_facade_metadata_admission is not None else {}),
        **({"sdk_android_metadata_admission": sdk_android_metadata_admission} if sdk_android_metadata_admission is not None else {}))
    return continuation_from_inspection(inspected, github_output_path,
        require_completed=require_completed, if_selected=if_selected,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))


def continuation_from_inspection(inspected, github_output_path, *, require_completed=False, if_selected=False,
                                 completed_frozen=None):
    """Route an already authenticated transition; no replay or transported trust."""
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
    completed_checkpoint = False
    if completed_frozen is not None:
        from reuse_qualification import CompletedFrozenReuse
        if type(completed_frozen) is not CompletedFrozenReuse:
            raise ValueError("Aggregate continuation requires concrete completed native evidence")
        completed_checkpoint = status == "completed" and completed_frozen.envelope(selected) is not None
    if status == "completed" and (completed_checkpoint or any(record["receiptSha256"] == receipt
            for record in inspected.get("runtimeAggregateReleaseEvidence", []))):
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
        "native_receipt_sha256s": canonical_json_bytes({target: {
            phase: phases[PhaseInstanceId("runtime", target, phase, target)]["receiptSha256"]
            for phase in ("binary", "package", "validation", "metadata")}
            for target in NATIVE_TARGETS}).decode().strip(),
    })
    return value


@verification_scoped
def capture(plan_path, destination, github_output_path, *, artifact_id, artifact_sha256,
            trusted_workflow_sha, state_wave=0, instance=None, expected_build_key=None,
            repository_root=None, environ=None, token, sdk_validation_tooling=None, sdk_apple_validation_policy=None,
            sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, continuation_mode=None,
            completed_frozen=None):
    if continuation_mode not in (None, "selected", "completed") or (
            continuation_mode is not None and (instance is not None or expected_build_key is not None)):
        raise ValueError("Runtime capture continuation requires an unselected routing invocation")
    tooling = {"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}
    if completed_frozen is not None:
        tooling["completed_frozen"] = completed_frozen
    if sdk_apple_validation_policy is not None:
        tooling["sdk_apple_validation_policy"] = sdk_apple_validation_policy
    tooling["sdk_original_workflow_sha"] = trusted_workflow_sha
    if sdk_facade_metadata_admission is not None:
        tooling["sdk_facade_metadata_admission"] = sdk_facade_metadata_admission
    if sdk_android_metadata_admission is not None:
        tooling["sdk_android_metadata_admission"] = sdk_android_metadata_admission
    products.capture_runtime_resume_upload(
        plan_path, destination, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
        trusted_workflow_sha=trusted_workflow_sha, state_wave=state_wave,
        repository_root=repository_root, environ=environ, token=token,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
    original = destination / "original"
    paths = {
        "input_root": original,
        "plan_path": original / "product-resume-inputs/plan/impact-plan.json",
        "discovery_root": original / "product-resume-state",
        "state_root": original / ("runtime-state" if state_wave else "product-resume-state"),
    }
    value = (matrix(paths["plan_path"], paths["discovery_root"], paths["state_root"], github_output_path,
                    repository_root=repository_root, environ=environ, **tooling)
             if continuation_mode is None else
             continuation(paths["plan_path"], paths["discovery_root"], paths["state_root"], github_output_path,
                 repository_root=repository_root, environ=environ, if_selected=continuation_mode == "selected",
                 require_completed=continuation_mode == "completed", **tooling))
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
            repository_root=None, environ=None, token, state_wave=None, sdk_validation_tooling=None,
            sdk_apple_validation_policy=None, sdk_facade_metadata_admission=None,
            sdk_android_metadata_admission=None, completed_frozen=None):
    tooling = {"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}
    if completed_frozen is not None:
        tooling["completed_frozen"] = completed_frozen
    if sdk_apple_validation_policy is not None:
        tooling["sdk_apple_validation_policy"] = sdk_apple_validation_policy
    tooling["sdk_original_workflow_sha"] = trusted_workflow_sha
    if sdk_facade_metadata_admission is not None:
        tooling["sdk_facade_metadata_admission"] = sdk_facade_metadata_admission
    if sdk_android_metadata_admission is not None:
        tooling["sdk_android_metadata_admission"] = sdk_android_metadata_admission
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
        **({"runtime_aggregate_only": True} if wave == 5 else {}), **tooling)
    if wave == 5 and (len(collection["rows"]) != 1 or products._identity(collection["rows"][0]) !=
                      PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")):
        raise ValueError("Runtime aggregate collection requires its sole elected aggregate row")
    shards = [destination / "collection" / row["shardDirectory"]
              for row in collection["rows"] if row["result"] == "success"]
    failures = tuple(products._identity(row) for row in collection["rows"] if row["result"] != "success")
    handoff = destination / "handoff"
    advanced = products.advance_products(
        plan, discovery, state, shards, handoff / "runtime-state", github_output_path,
        repository_root=repository_root, environ=environ, failed_instances=failures, routing_output=True,
        runtime_collection_wave=wave,
        **({"runtime_aggregate_only": True} if wave == 5 else {"runtime_workers_only": True}), **tooling)
    # Original input and receipt bytes are forwarded, not regenerated. Collection
    # diagnostics have their own upload, avoiding recursively nested wave archives.
    for name in ("product-resume-inputs", "product-resume-state"):
        products.snapshot_reuse_inputs(input_root / name, handoff / name, completed_frozen=completed_frozen)
    if wave == 5:
        if failures:
            github_output(github_output_path, {
                "native_attestation_matrix": '{"include":[]}',
                "aggregate_state": "failed", "aggregate_key": "", "aggregate_receipt_sha256": "",
                "aggregate_required": False, "aggregate_payload_complete": False,
            })
    elif failures:
        github_output(github_output_path, {"runtime_matrix": '{"include":[]}',
                                          "runtime_workers_required": False, "supervisor_key": ""})
    # advance_products emits the route from its completed full replay and
    # enforces the final worker/aggregate-wave gates before publishing state.
    return advanced


@verification_scoped
def main(argv=None):
    from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--plan", type=Path, required=True)
    preflight.add_argument("--product", required=True)
    preflight.add_argument("--wave", type=int, required=True)
    preflight.add_argument("--family")
    preflight.add_argument("--trusted-workflow-sha", required=True)
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
    captured.add_argument("--continuation", choices=("selected", "completed"))
    captured.add_argument("--sdk-validation-tooling", type=Path)
    for name in ("component", "phase", "target", "expected-build-key"):
        captured.add_argument(f"--{name}")
    collected = commands.add_parser("collect")
    for name in ("input-root", "destination", "github-output"):
        collected.add_argument(f"--{name}", type=Path, required=True)
    collected.add_argument("--wave", type=int, required=True)
    collected.add_argument("--state-wave", type=int)
    collected.add_argument("--trusted-workflow-sha", required=True)
    collected.add_argument("--sdk-validation-tooling", type=Path)
    for command in (show, final, captured, collected):
        command.add_argument("--sdk-apple-validation-policy", type=Path)
        add_metadata_admission_arguments(command)
    for command in (show, final):
        command.add_argument("--sdk-original-workflow-sha")
    trust = commands.add_parser("variant-trust")
    trust.add_argument("--variant-handoff", action="append", required=True, metavar="TARGET=PATH")
    for name in ("destination", "keyring", "keys-directory"):
        trust.add_argument(f"--{name}", type=Path, required=True)
    retained = commands.add_parser("recover-native-handoffs")
    for name in ("plan", "destination", "github-output"):
        retained.add_argument(f"--{name}", type=Path, required=True)
    retained.add_argument("--trusted-workflow-sha", required=True)
    retained.add_argument("--recovery-json", required=True)
    retained.add_argument("--selected-receipts-json", required=True)
    referenced = commands.add_parser("export-references")
    for name in ("handoff", "base-root", "base-capture", "destination"):
        referenced.add_argument(f"--{name}", type=Path, required=True)
    referenced.add_argument("--state-wave", type=int, required=True)
    referenced.add_argument("--sdk-state-wave", type=int)
    for command in (show, final, captured, collected):
        add_completed_frozen_argument(command)
    args = parser.parse_args(argv)
    try:
        apple_policy = ({} if getattr(args, "sdk_apple_validation_policy", None) is None else {
            "sdk_apple_validation_policy": products._canonical_control(
                args.sdk_apple_validation_policy, "Caller Apple validation policy")})
        if args.command == "preflight":
            products.preflight_worker_uploads(args.plan, product=args.product, wave=args.wave,
                family=args.family, trusted_workflow_sha=args.trusted_workflow_sha,
                token=os.environ.get("GITHUB_TOKEN"))
        elif args.command == "export-references":
            from runtime_reference_transport import stage_reference_handoff
            stage_reference_handoff(args.handoff, args.base_root, args.base_capture,
                                    args.destination, state_wave=args.state_wave, sdk_state_wave=args.sdk_state_wave)
        elif args.command == "matrix":
            tooling = ({} if args.sdk_validation_tooling is None else {"sdk_validation_tooling":
                products._canonical_control(args.sdk_validation_tooling, "Caller SDK tooling policy")})
            with metadata_admission_options(args) as admissions, completed_frozen_options(args) as semantic:
                matrix(args.plan, args.discovery_root, args.state_root, args.github_output,
                       **tooling, **apple_policy, **semantic,
                       **({"sdk_original_workflow_sha": args.sdk_original_workflow_sha}
                          if args.sdk_original_workflow_sha is not None else {}), **admissions)
        elif args.command == "continuation":
            tooling = (None if args.sdk_validation_tooling is None else
                       products._canonical_control(args.sdk_validation_tooling, "Caller SDK tooling policy"))
            with metadata_admission_options(args) as admissions, completed_frozen_options(args) as semantic:
                continuation(args.plan, args.discovery_root, args.state_root, args.github_output,
                             sdk_validation_tooling=tooling, **semantic, **({"if_selected": True} if args.if_selected else {}),
                             **({"require_completed": True} if args.require_completed else {}),
                             **apple_policy,
                             **({"sdk_original_workflow_sha": args.sdk_original_workflow_sha}
                                if args.sdk_original_workflow_sha is not None else {}), **admissions)
        elif args.command == "capture":
            tooling = ({} if args.sdk_validation_tooling is None else {"sdk_validation_tooling":
                products._canonical_control(args.sdk_validation_tooling, "Caller SDK tooling policy")})
            values = (args.component, args.phase, args.target, args.expected_build_key)
            if any(value is not None for value in values) and any(value is None for value in values):
                raise ValueError("All four elected worker arguments are required")
            with metadata_admission_options(args) as admissions, completed_frozen_options(args) as semantic:
                capture(args.plan, Path(os.path.abspath(args.destination)), args.github_output,
                        artifact_id=args.artifact_id, artifact_sha256=args.artifact_sha256,
                        trusted_workflow_sha=args.trusted_workflow_sha, state_wave=args.state_wave,
                        instance=PhaseInstanceId("runtime", *values[:3]) if all(values) else None,
                        expected_build_key=args.expected_build_key, token=os.environ.get("GITHUB_TOKEN", ""),
                        **({"continuation_mode": args.continuation} if args.continuation is not None else {}),
                        **tooling, **apple_policy, **admissions, **semantic)
        elif args.command == "recover-native-handoffs":
            from runtime_preparation_capture import capture_runtime_native_release_handoffs
            capture_runtime_native_release_handoffs(args.plan, args.destination,
                recovery=load_json_bytes(args.recovery_json.encode("utf-8")),
                selected_receipt_sha256s=load_json_bytes(args.selected_receipts_json.encode("utf-8")),
                trusted_workflow_sha=args.trusted_workflow_sha, token=os.environ.get("GITHUB_TOKEN", ""))
            github_output(args.github_output, {"native_attestation_matrix": '{"include":[]}'})
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
            tooling = ({} if args.sdk_validation_tooling is None else {"sdk_validation_tooling":
                products._canonical_control(args.sdk_validation_tooling, "Caller SDK tooling policy")})
            with metadata_admission_options(args) as admissions, completed_frozen_options(args) as semantic:
                collect(Path(os.path.abspath(args.input_root)), Path(os.path.abspath(args.destination)), args.github_output,
                        wave=args.wave, trusted_workflow_sha=args.trusted_workflow_sha,
                        token=os.environ.get("GITHUB_TOKEN", ""),
                        **({"state_wave": args.state_wave} if args.state_wave is not None else {}),
                        **tooling, **apple_policy, **admissions, **semantic)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
