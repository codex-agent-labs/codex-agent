"""Locate fixed Apple uploads; never admit or download product contents."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_integer, require_sha256,
)
from products.signing_isolation import require_no_signing_secret
from reuse import github_output


RETAINED_VALIDATION_UPLOADS = {
    "ios-arm64": (
        "sha256:1bbea1cdeb61cbd908f49480fb89fffa58c3da28de34cc42a7d0e58559ecad16",
        11934933559, "sha256:4f1ce4fc26eeb622978509d5e1a937d1f6729041694393dc8667befb6ccf14d0", 116144183690),
    "ios-simulator-arm64": (
        "sha256:e7958fc10f983e5ddc41714a80587eacf8cd9ccd715b1829873113fd606917b7",
        11935475988, "sha256:1b4e95d83b250735dd0892127b89769cff1800d54993394bc89f2ffe03d67de8", 116144183702),
}

# Exact raw receipts in the fully SHA-verified ios-arm64 original 11934933559.
# These reviewed content pins enable scoped transport, not semantic admission.
# Consumption additionally requires the matching native-qualified phase and
# fresh original job/workflow/upload observation. Never derive raw receipts
# from the deterministic projection, which intentionally omits execution hashes.
RETAINED_PARITY_ARCHIVE_BYTES = 1610548650
RETAINED_PARITY_REPORTS = (
    {"relativePath": "reports/objective-c-parity.json", "bytes": 438015,
     "sha256": "sha256:614ed737ce103c271bedcb339afca9add2bf27e2c2a6f2ecbff520ed119b208a"},
    {"relativePath": "reports/swift-parity.json", "bytes": 439042,
     "sha256": "sha256:02b59f4974855a394fa8be194cfd3d22d045f6727dac925b9964b4fd274c32b9"},
)


def retained_validation_origin(target, build_key, consumer):
    """Select two reviewed successful uploads; selection grants no admission.

    Each consumer still observes the original job/upload and authenticates its
    complete bytes. Keep the original producer and receipt when signing later.
    """
    row = RETAINED_VALIDATION_UPLOADS.get(target)
    producer = {"repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
        "commit": "1f8c236eca5e2651bbfc18afb8b8232526445537", "tree": "6ba89c3ff4c8cb9b30f7216641ac3461c0d94206",
        "event": "pull_request", "runId": 38649218072, "runAttempt": 1, "pullRequest": 31}
    if (row is None or row[0] != build_key
            or any(consumer.get(name) != producer[name] for name in ("repository", "workflowPath", "event", "pullRequest"))
            or any(type(consumer.get(name)) is not int or consumer[name] < 1 for name in ("runId", "runAttempt"))
            or (consumer["runId"], consumer["runAttempt"]) <= (producer["runId"], producer["runAttempt"])):
        return None
    return {"producer": producer, "artifact_id": row[1], "artifact_sha256": row[2], "job_id": row[3],
            "workflow_sha": "950d5d73b96d95d99c38156297f3bcd6031e19f1"}


def retained_validation_attestation_origin(target, build_key, consumer):
    """Keep the two completed protected signatures when later collection fails."""
    worker = retained_validation_origin(target, build_key, consumer)
    if worker is None:
        return None
    producer = {**worker["producer"], "commit": "38045b7856bf12a6007306df07661f2f71672c0b",
        "tree": "8a0c0ba0fb7446dfe83d689ef624d96e553a7342", "runId": 38660614466, "runAttempt": 1}
    if (consumer["runId"], consumer["runAttempt"]) <= (producer["runId"], producer["runAttempt"]):
        return None
    row = {
        "ios-arm64": (11939829176, "sha256:9d3a933a94186474d41c5bb648d683e4182d9cbb7ee73d98ab1a0990bc376f6e",
            3225406781, 116186904230, "sha256:f4d24e7f2f09630811e0d930a86f1f8964711898b6577ee48e386d86b8926be0"),
        "ios-simulator-arm64": (11939862672, "sha256:2a98b32a3f2f1494c0259c9db060bea29ef15f549e1ad7a10572860b6ef99526",
            3225851351, 116186904368, "sha256:0088a74dbd328828ba42ca6bf83d166f09aa1f50eceb206bea94659af97243c4"),
    }[target]
    return {"producer": producer, "artifact_id": row[0], "artifact_sha256": row[1],
        "artifact_bytes": row[2], "job_id": row[3], "receipt_sha256": row[4],
        "workflow_sha": "0217db8b553dfe4ed3a09b6531636ff5aa7e2ede"}


def observe_retained_validation_attestation(target, build_key, consumer, *, token):
    """Fresh fixed-origin routing only; full capture/signature/admission follow."""
    origin = retained_validation_attestation_origin(target, build_key, consumer)
    if origin is None:
        return None
    producer = origin["producer"]
    job = f"product-validation / sdk-apple-validation-attestation-{target}"
    observed = products._observe_ci_producer_jobs({"attestation": producer},
        jobs_by_phase={"attestation": job}, trusted_workflow_sha=origin["workflow_sha"], token=token)
    jobs = [value for value in observed[0]["jobs"] if value.get("name") == job]
    if len(jobs) != 1 or jobs[0].get("id") != origin["job_id"]:
        raise ValueError("Retained Apple attestation differs from its reviewed successful job")
    name = (f"codex-agent-sdk-apple-validation-evidence-{target}-{origin['receipt_sha256'][7:]}-"
            f"{producer['tree']}-attempt-{producer['runAttempt']}")
    artifact = products._contract_ci_upload_metadata(origin["artifact_id"], origin["artifact_sha256"],
        name, producer, observed[0]["run"], token)
    products._require_artifact_job_window(observed[0], job, artifact)
    if artifact["size_in_bytes"] != origin["artifact_bytes"]:
        raise ValueError("Retained Apple attestation differs from its reviewed upload size")
    return {**origin, "artifact": artifact, "observed": observed}


def _locate(producer, *, phase, job, name, token, trusted_workflow_sha=None,
            trusted_workflows_by_phase=None, expected_build_key=None, expected_job_id=None):
    """Shared fixed-callsite observation/list/detail/window checks, no downloads."""
    producer_bytes = canonical_json_bytes(producer)
    observation = products._observe_ci_producer_jobs({phase: producer},
        jobs_by_phase={phase: job}, trusted_workflow_sha=trusted_workflow_sha,
        trusted_workflows_by_phase=trusted_workflows_by_phase, token=token,
        **({"build_keys_by_phase": {phase: expected_build_key}} if expected_build_key is not None else {}))[0]
    if expected_build_key is not None:
        matching = products._matching_ci_jobs(observation["jobs"], job, expected_build_key=expected_build_key)
        if len(matching) != 1:
            raise ValueError("Apple original worker job is missing or ambiguous")
        if expected_job_id is not None and matching[0].get("id") != expected_job_id:
            raise ValueError("Apple original worker differs from its reviewed successful job")
        job = matching[0]["name"]
    api = f"https://api.github.com/repos/{producer['repository']}/actions"
    artifacts = products.paginated_items(f"{api}/runs/{producer['runId']}/artifacts", "artifacts", token)
    selected = [value for value in artifacts if type(value) is dict
                and value.get("name") == name and value.get("expired") is False]
    if len(selected) != 1:
        raise ValueError("Apple original upload is missing or ambiguous")
    listed = selected[0]
    artifact_id = require_integer(listed.get("id"), "Apple upload ID", 1)
    digest = require_sha256(listed.get("digest"), "Apple upload digest")
    url = f"{api}/artifacts/{artifact_id}"
    detail = products.api_json(url, token)
    if (type(detail) is not dict or any(detail.get(field) != listed.get(field) for field in (
            "id", "name", "digest", "expired", "workflow_run", "created_at"))
            or detail.get("archive_download_url") != url + "/zip"
            or type(detail.get("workflow_run")) is not dict
            or require_integer(detail["workflow_run"].get("id"), "Apple upload run", 1) != producer["runId"]
            or detail["workflow_run"].get("head_sha") != observation["run"]["head_sha"]):
        raise ValueError("Apple upload differs from its observed run or listing")
    products._require_artifact_job_window(observation, job, detail)
    if canonical_json_bytes(producer) != producer_bytes:
        raise ValueError("Apple upload producer changed during observation")
    return {"artifact_id": artifact_id, "artifact_sha256": digest}


def locate_original_apple_upload(receipt_path, *, trusted_workflow_sha, token, environ=None):
    """Locate the selected original iOS binary/package upload, not current work.

    The caller must independently authenticate/select the original receipt.
    Canonical structure and official upload metadata do not replace recapture
    and complete original content admission. Current environment cannot relabel
    the receipt's producer, build key, run or attempt.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if type(token) is not str or not token:
        raise ValueError("Apple upload locator requires an observation token")
    receipt_path = Path(receipt_path).absolute()
    raw = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt = products.validate_phase_receipt(load_canonical_json_bytes(raw))
    if ((receipt["product"], receipt["component"], receipt["target"]) != ("sdk", "sdk-ios", "ios")
            or receipt["phase"] not in ("binary", "package")):
        raise ValueError("Original Apple upload locator requires an exact iOS binary or package receipt")
    producer, phase = receipt["producer"], receipt["phase"]
    job = f"product-validation / sdk-sdk-ios-{phase}-ios"
    name = (f"codex-agent-sdk-worker-sdk-ios-{phase}-ios-{receipt['buildKey'].removeprefix('sha256:')}-"
            f"{producer['tree']}-attempt-{producer['runAttempt']}")
    result = _locate(producer, phase=phase, job=job, name=name,
                     trusted_workflow_sha=trusted_workflow_sha, token=token,
                     expected_build_key=receipt["buildKey"])
    require_no_signing_secret(environment)
    if (read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != raw
            or canonical_json_bytes(receipt) != raw):
        raise ValueError("Original Apple receipt changed during observation")
    return result


def locate_apple_upload(plan_path, candidate_root, *, mode, target,
        trusted_workflow_sha, expected_build_key=None, environ=None, token):
    """Return only an official locator; consumption must independently recapture.

    The producer is the current authorized plan/environment or its exact
    reviewed retained success. Uploaded receipts, matrix outputs and newest-run
    heuristics cannot select a producer or replace the original upload pins.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if mode not in ("validation", "preparation"):
        raise ValueError("Apple upload locator requires validation or preparation mode")
    if target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Apple upload locator requires an exact validation target")
    if mode == "validation":
        require_sha256(expected_build_key, "Selected Apple validation build key")
    elif expected_build_key is not None:
        raise ValueError("Apple preparation locator does not accept a build key")
    if type(token) is not str or not token:
        raise ValueError("Apple upload locator requires an observation token")
    candidate = Path(candidate_root).resolve(strict=True)
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="apple-upload-locator-") as temporary:
        captured_plan = Path(temporary).resolve() / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = products._validate_plan(captured_plan, candidate)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}:
            raise ValueError("Apple upload locator requires an authorized PR or merge-group plan")
        plan_value = canonical_json_bytes(plan)
        producer = products.validate_producer(products._consumer(plan, environment)["producer"])
        current_producer = dict(producer)
        origin = None
        if mode == "validation":
            origin = retained_validation_origin(target, expected_build_key, producer)
            if origin is not None:
                producer = origin["producer"]
            job = f"product-validation / sdk-sdk-ios-validation-{target}"
            name = (f"codex-agent-sdk-worker-sdk-ios-validation-{target}-"
                    f"{expected_build_key.removeprefix('sha256:')}-{producer['tree']}-attempt-{producer['runAttempt']}")
        else:
            job = f"product-validation / sdk-apple-signing-prepare-{target}"
            name = (f"codex-agent-sdk-apple-signing-preparation-{target}-"
                    f"{producer['tree']}-attempt-{producer['runAttempt']}")
        result = _locate(producer, phase=mode, job=job, name=name,
                         trusted_workflow_sha=origin["workflow_sha"] if origin else trusted_workflow_sha, token=token,
                         expected_build_key=expected_build_key,
                         **({"expected_job_id": origin["job_id"]} if origin else {}))
        if origin is not None and result != {name: origin[name] for name in ("artifact_id", "artifact_sha256")}:
            raise ValueError("Apple original upload differs from its reviewed successful artifact")
        require_no_signing_secret(environment)
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(captured_plan) != plan_bytes
                or canonical_json_bytes(plan) != plan_value
                or products.validate_producer(products._consumer(plan, environment)["producer"]) != current_producer):
            raise ValueError("Apple locator plan or current producer changed during observation")
    return result


def _digest(value):
    try:
        return require_sha256(value, "Apple validation build key")
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    modes = parser.add_subparsers(dest="mode", required=True)
    for mode in ("validation", "preparation"):
        command = modes.add_parser(mode, allow_abbrev=False)
        for name in ("plan", "candidate-root"):
            command.add_argument(f"--{name}", type=Path, required=True)
        command.add_argument("--target", choices=("ios-arm64", "ios-simulator-arm64"), required=True)
        command.add_argument("--trusted-workflow-sha", required=True)
        command.add_argument("--github-output", type=Path)
        if mode == "validation":
            command.add_argument("--expected-build-key", type=_digest, required=True)
    args = parser.parse_args(argv)
    try:
        value = locate_apple_upload(args.plan, args.candidate_root, mode=args.mode, target=args.target,
            trusted_workflow_sha=args.trusted_workflow_sha,
            **({"expected_build_key": args.expected_build_key} if args.mode == "validation" else {}),
            environ=os.environ, token=os.environ["GITHUB_TOKEN"])
        if args.github_output is None:
            print(canonical_json_bytes(value).decode().strip())
        else:
            github_output(args.github_output, value)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
