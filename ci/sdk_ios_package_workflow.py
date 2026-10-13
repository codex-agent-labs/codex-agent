"""Compose the existing authenticated inputs, iOS package worker and full gate."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
import time

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_workflow
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys, sha256_bytes,
)
from products.sdk_apple_package_execution import build_apple_package_execution_context
from products.registry import PhaseInstanceId
from products.restore import (
    PHASE_PLAN_KEYS, PHASE_RECEIPT_NAME, PHASE_SHARD_KEYS, object_relative_path,
    restore_object, verify_phase_shard,
)
from products.sdk_inputs import REQUEST_NAME
from products.sdk_package import verify_sdk_package_inputs
from sdk_ios_package import execute as execute_package


_INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")


def recover_unverified_package(plan, ready, producer, version, destination, *, token, work_directory):
    """Recover byte inputs, NOT a successful phase or an admission capability.

    Range transport does not authenticate the whole outer ZIP. The old receipt
    remains an untrusted production claim. Only the caller's fresh full package
    gate and successful job can establish a new completion under its own producer.
    """
    from sdk_ios_binary_recovery import _require_prior
    from runtime_reference_archive import copy_reference_member, open_reference_archive

    started = time.monotonic_ns()
    prefix = product_reuse._worker_artifact_prefix("sdk", _INSTANCE) + ready["buildKey"][7:] + "-"
    found = []
    for prior in product_reuse._iter_prior_failed_pr_attempts(
            plan, producer, token, required_artifact_prefixes=(prefix,)):
        run, attempt = _require_prior(plan, producer, prior)
        url = f"https://api.github.com/repos/{plan['repository']}/actions/runs/{run}"
        uploads = product_reuse.paginated_items(url + "/artifacts", "artifacts", token)
        matching = [row for row in uploads if row.get("expired") is False
                    and row.get("name", "").startswith(prefix)
                    and row["name"].endswith(f"-attempt-{attempt}")]
        if len(matching) != 1:
            raise ValueError("Unverified Apple package upload is missing or ambiguous")
        listed = matching[0]
        artifact = product_reuse._contract_ci_upload_metadata(
            listed["id"], listed["digest"], listed["name"], {"runId": run}, prior, token)
        jobs = product_reuse.paginated_items(url + f"/attempts/{attempt}/jobs", "jobs", token)
        jobs = product_reuse._matching_ci_jobs(jobs,
            "product-validation / sdk-sdk-ios-package-ios", expected_build_key=ready["buildKey"])
        if len(jobs) != 1 or jobs[0].get("status") != "completed":
            raise ValueError("Unverified Apple package job is missing or ambiguous")
        job = jobs[0]
        if job.get("conclusion") == "success":
            raise ValueError("Successful Apple package exists; recover it through original admission first")
        if (job.get("conclusion") not in {"failure", "cancelled"}
                or job.get("run_id") != run or job.get("head_sha") != prior["head_sha"]):
            raise ValueError("Unverified Apple package job differs from its official failed attempt")
        product_reuse._require_artifact_job_window({"jobs": jobs}, job["name"], artifact)
        with open_reference_archive(artifact, token) as (archive, _):
            names = set(archive.namelist())
            if ("unverified-package/phase-object.json" not in names
                    or "worker/execution.json" not in names):
                continue  # Older failure did not preserve produced package bytes.
            controls = {}
            control_names = ["unverified-package/phase-object.json",
                             "unverified-package/phase-receipt.json", "worker/execution.json",
                             "worker/gradle.log"]
            control_names.extend(name for name in sorted(names) if name.startswith((
                "package-execution/events/00-toolchain-before-xcode/",
                "package-execution/events/01-toolchain-before-swift/")) and not name.endswith("/"))
            if len(control_names) > 16:
                raise ValueError("Unverified Apple package diagnostics exceed their member bound")
            for name in control_names:
                if archive.getinfo(name).file_size > 16 * 1024**2:
                    raise ValueError("Unverified Apple package control exceeds its bound")
                controls[name] = archive.read(name)
            receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(
                controls["unverified-package/phase-receipt.json"]))
            origin = receipt["producer"]
            if ({name: receipt[name] for name in PHASE_PLAN_KEYS} != ready
                    or receipt["productVersion"] != version
                    or origin["runId"] != run
                    or origin["runAttempt"] != attempt or origin["pullRequest"] != plan["pullRequest"]
                    or origin["repository"] != plan["repository"] or origin["event"] != "pull_request"
                    or artifact["name"] != prefix + origin["tree"] + f"-attempt-{attempt}"):
                raise ValueError("Unverified Apple package differs from current inputs or original producer")
            tested = product_reuse._observe_tested_commit(
                prior, api="https://api.github.com", repository=plan["repository"], token=token,
                expected_commit=origin["commit"], expected_tree=origin["tree"],
                pull_request=origin["pullRequest"])
            execution = load_canonical_json_bytes(controls["worker/execution.json"])
            if (execution.get("producer") != origin or execution.get("buildKey") != ready["buildKey"]
                    or execution.get("returnCode") != 0 or execution.get("launchError") is not None):
                raise ValueError("Unverified Apple package has no successful production observation")
            descriptor = require_exact_keys(load_canonical_json_bytes(
                controls["unverified-package/phase-object.json"]), PHASE_SHARD_KEYS,
                "Unverified Apple package object")
            digest = sha256_bytes(controls["unverified-package/phase-receipt.json"])
            object_path = object_relative_path(ready["buildKey"], digest)
            if (descriptor["objectPath"] != object_path or descriptor["receiptSha256"] != digest
                    or descriptor["buildKey"] != ready["buildKey"]):
                raise ValueError("Unverified Apple package object differs from its original receipt")
            found.append((artifact, job, prior, controls, receipt, descriptor, object_path, tested))
    if not found:
        return None
    if any(row[4]["outputs"] != found[0][4]["outputs"] for row in found[1:]):
        raise ValueError("Unverified Apple packages conflict for the same build key")
    artifact, job, prior, controls, receipt, descriptor, object_path, tested = found[0]
    destination.mkdir(parents=True, exist_ok=False)
    original = destination / "production-origin"
    original.mkdir()
    for name, raw in controls.items():
        target = original / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(raw)
    # Body/stage are private working inputs, not extra multi-GB upload copies.
    body = work_directory / "unverified-package"
    body.mkdir(parents=True, exist_ok=False)
    for name in ("phase-object.json", "phase-receipt.json"):
        with (body / name).open("xb") as output:
            output.write(controls["unverified-package/" + name])
    with open_reference_archive(artifact, token) as (archive, stream):
        member = "unverified-package/" + object_path
        copy_reference_member(archive, member, body / object_path,
            {"bytes": archive.getinfo(member).file_size, "sha256": descriptor["objectSha256"]})
        transferred = stream.transferred
    verified = verify_phase_shard(body, _INSTANCE)
    stage = work_directory / "stage"
    restore_object(body / object_path, stage,
        build_key=ready["buildKey"], receipt_sha256=descriptor["receiptSha256"],
        object_sha256=descriptor["objectSha256"])
    product_reuse.write_canonical_json(original / "transport.json", {
        "kind": "untrusted-package-production-input", "artifact": artifact,
        "run": prior, "job": job, "testedCommit": tested, "wholeOuterArchiveVerified": False,
        "originalReceiptSha256": descriptor["receiptSha256"],
        "objectSha256": descriptor["objectSha256"], "rangeBytes": transferred,
        "elapsedNs": time.monotonic_ns() - started,
    })
    print(f"Recovered untrusted Apple package input from artifact {artifact['id']}; "
          f"{transferred} range bytes, {(time.monotonic_ns() - started) // 1_000_000}ms; "
          "production skipped, full fresh package gate still required", flush=True)
    return {"stage": stage, "outputInventory": regular_file_inventory(stage),
            "outputs": verified["receipt"]["outputs"],
            "originInventory": regular_file_inventory(original, allow_empty=True)}


def execute(
    plan: Path, discovery: Path, state: Path, destination: Path, *,
    expected_build_key: str,
    sdk_inputs_artifact_id: int, sdk_inputs_artifact_sha256: str,
    trusted_workflow_sha: str,
    keyring: Path, keys_directory: Path, developer_directory: Path,
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, repository_root: Path, environ: dict, token: str,
    required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
    sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
    retained_sdk_inputs_source=None,
    completed_frozen=None,
) -> dict:
    """Build and admit one elected package; publish only after all contexts close."""
    root = Path(repository_root).resolve(strict=True)
    developer_directory = Path(developer_directory)
    if (not developer_directory.is_absolute() or not developer_directory.is_dir()
            or developer_directory.resolve(strict=True) != developer_directory):
        raise ValueError("Apple Developer directory must be absolute, normalized and non-symbolic")
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination,
    )
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK iOS package destination must not exist")
    plan_bytes = read_regular_file_bytes(Path(plan), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)

    tooling = {"evidence": str(Path(tooling_evidence).absolute()),
        "publicKey": str(Path(tooling_public_key).absolute()),
        "javaExecutable": str(Path(java_executable).absolute()),
        "requiredTrustDomain": required_trust_domain,
        "keyring": str(Path(tooling_keyring).absolute()) if tooling_keyring is not None else None,
        "keysDirectory": str(Path(tooling_keys_directory).absolute()) if tooling_keys_directory is not None else None}
    apple = ({} if sdk_apple_validation_policy is None else
             {"sdk_apple_validation_policy": sdk_apple_validation_policy})
    admissions = {name: value for name, value in (
        ("sdk_facade_metadata_admission", sdk_facade_metadata_admission),
        ("sdk_android_metadata_admission", sdk_android_metadata_admission),
    ) if value is not None}
    with tempfile.TemporaryDirectory(prefix="sdk-ios-package-candidate-") as temporary:
        candidate = Path(temporary).resolve() / "shard"
        with sdk_workflow.verified_inputs(
            plan, discovery, state, requested_scope=(_INSTANCE,), artifact_id=sdk_inputs_artifact_id,
            artifact_sha256=sdk_inputs_artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
            keys_directory=keys_directory, repository_root=root,
            environ=environ, token=token, sdk_validation_tooling=tooling,
            **apple, **admissions,
            **({"retained_sdk_inputs_source": retained_sdk_inputs_source}
               if retained_sdk_inputs_source is not None else {}),
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
        ) as sdk_inputs:
            selection = sdk_inputs["selection"]
            selected = {"product": "sdk", "component": "sdk-ios", "phase": "package", "target": "ios"}
            if selected not in selection["consumers"]:
                raise ValueError("SDK iOS package is not selected")
            prepared = destination / "inputs"
            ready = product_reuse.materialize_product_predecessors(
                plan, discovery, state, _INSTANCE, prepared,
                expected_build_key=expected_build_key,
                repository_root=root, environ=environ, sdk_validation_tooling=tooling,
                sdk_original_workflow_sha=trusted_workflow_sha,
                **apple, **admissions,
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
            )
            prepared_inventory = regular_file_inventory(prepared, allow_empty=True)
            producer = product_reuse.validate_producer(product_reuse._canonical_control(
                prepared / "producer.json", "Elected SDK iOS package producer",
            ))

            def original(product, component, phase, target):
                directory = prepared / "-".join((product, component, phase, target))
                receipt_path = directory / PHASE_RECEIPT_NAME
                receipt = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
                    receipt_path, "Original SDK iOS package predecessor",
                ))
                if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
                    product, component, phase, target,
                ):
                    raise ValueError("SDK iOS package predecessor has the wrong identity")
                manifest = product_reuse.verify_output_manifest_identity(
                    directory / "stage", product, component, phase, target, receipt["productVersion"],
                )
                if manifest["outputs"] != receipt["outputs"]:
                    raise ValueError("SDK iOS package predecessor differs from its original receipt")
                return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

            contract_metadata = original("contract", "contract", "metadata", "common")
            contract_binary = original("contract", "contract", "binary", "common")
            sdk_binary = original("sdk", "sdk-ios", "binary", "ios")
            arguments = sdk_inputs["sdk"]["arguments"]
            read_regular_file_bytes(
                arguments["contract_payload"], max_bytes=512 * 1024 * 1024,
                reject_symlink_parents=True,
            )
            if read_regular_file_bytes(contract_metadata["receiptPath"]) != read_regular_file_bytes(
                    arguments["contract_metadata_receipt"]):
                raise ValueError("Current Contract predecessor differs from authenticated SDK inputs")
            contract_evidence = {
                "stageRoot": str(contract_metadata["stage"]),
                "phaseReceipt": str(contract_metadata["receiptPath"]),
                "attestation": str(arguments["contract_attestation"]),
                "attestationSignature": str(arguments["contract_attestation_signature"]),
                "publicKey": str(arguments["contract_public_key"]),
                "expectedTrustDomain": arguments["required_trust_domain"],
                "keyring": str(arguments["contract_keyring"]) if arguments["contract_keyring"] else None,
                "keysDirectory": str(arguments["contract_keys_directory"])
                if arguments["contract_keys_directory"] else None,
            }
            if regular_file_inventory(prepared, allow_empty=True) != prepared_inventory:
                raise ValueError("SDK iOS package predecessors changed during Contract verification")
            recovered = recover_unverified_package(
                product_reuse._validate_plan(Path(plan), root), ready, producer,
                selection["sdkVersion"], destination / "recovered-production", token=token,
                work_directory=candidate.parent / "recovered-production",
            )
            result = recovered if recovered is not None else execute_package(
                ready, producer=producer, sdk_version=selection["sdkVersion"],
                current_contract=contract_binary, sdk_binary=sdk_binary,
                compatibility_request=sdk_inputs["sdk"]["directory"] / REQUEST_NAME,
                repository_root=root, destination=destination / "worker",
                environ={**environ, "DEVELOPER_DIR": str(developer_directory)},
            )
            if regular_file_inventory(prepared, allow_empty=True) != prepared_inventory:
                raise ValueError("SDK iOS package authenticated inputs changed during execution")
            trust = "development" if producer["event"] == "pull_request" else "release"
            finalized = product_reuse.finalize_phase_object(
                stage_root=result["stage"], phase_plan=ready, producer=producer,
                product_version=selection["sdkVersion"], trust_domain=trust,
                destination=candidate,
            )
            if recovered is not None and finalized["receipt"]["outputs"] != recovered["outputs"]:
                raise ValueError("Apple package completion changed the preserved output inventory")
            apple_verification = {
                "developer_directory": Path(developer_directory),
                "repository": root,
                "tooling_evidence": Path(tooling_evidence),
                "tooling_public_key": Path(tooling_public_key),
                "java_executable": Path(java_executable),
                "policy_revision": policy_revision,
                "required_trust_domain": required_trust_domain,
                "tooling_keyring": tooling_keyring,
                "tooling_keys_directory": tooling_keys_directory,
            }
            try:
                verified, raw = verify_sdk_package_inputs(
                    root, result["stage"], candidate / PHASE_RECEIPT_NAME,
                    sdk_inputs["sdk"]["directory"] / REQUEST_NAME,
                    binary_stage_root=sdk_binary["stage"],
                    binary_receipt_path=sdk_binary["receiptPath"],
                    binary_contract_evidence=contract_evidence,
                    apple_binary_verification=apple_verification,
                    apple_execution_capture_directory=destination / "package-execution",
                )
            except Exception as failure:
                # Preserve produced bytes for diagnosis, never publish an admitted shard.
                try:
                    publish_regular_tree(candidate, destination / "unverified-package")
                except Exception as custody_failure:
                    failure.add_note(f"Unverified package preservation failed: {custody_failure}")
                raise
            if (verified != finalized["receipt"] or raw != read_regular_file_bytes(
                    candidate / PHASE_RECEIPT_NAME)):
                raise ValueError("SDK iOS package gate returned a different candidate receipt")
            execution_context = build_apple_package_execution_context(
                capture_directory=destination / "package-execution",
                package_receipt=candidate / PHASE_RECEIPT_NAME,
                binary_receipt=sdk_binary["receiptPath"],
                contract_binary_receipt=contract_binary["receiptPath"],
                contract_metadata_receipt=contract_metadata["receiptPath"],
                producer=producer,
                sdk_compatibility=result["stage"] / "outputs/evidence/sdk-compatibility.json",
                sdk_inputs_artifact_id=sdk_inputs_artifact_id,
                sdk_inputs_artifact_sha256=sdk_inputs_artifact_sha256,
            )
            context_bytes = canonical_json_bytes(execution_context)
            context_path = destination / "apple-package-execution.json"
            with context_path.open("xb") as context_file:
                context_file.write(context_bytes)
            if read_regular_file_bytes(Path(plan), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
                raise ValueError("SDK iOS package original plan changed during verification")
            retained_plan = destination / "original-plan/impact-plan.json"
            retained_plan.parent.mkdir()
            with retained_plan.open("xb") as plan_file:
                plan_file.write(plan_bytes)
            candidate_inventory = regular_file_inventory(candidate)
            if regular_file_inventory(prepared, allow_empty=True) != prepared_inventory:
                raise ValueError("SDK iOS package authenticated inputs changed before publication")
        if regular_file_inventory(prepared, allow_empty=True) != prepared_inventory:
            raise ValueError("SDK iOS package authenticated inputs changed after SDK verification")
        if (regular_file_inventory(result["stage"], allow_empty=True) != result["outputInventory"]
                or regular_file_inventory(candidate) != candidate_inventory
                or verify_phase_shard(candidate, _INSTANCE) != finalized):
            raise ValueError("SDK iOS package candidate changed after admission")
        if recovered is not None and regular_file_inventory(
                destination / "recovered-production/production-origin", allow_empty=True) != recovered["originInventory"]:
            raise ValueError("Apple package original production evidence changed during completion")
        if (regular_file_inventory(destination / "package-execution", allow_empty=True) != execution_context["captureFiles"]
                or read_regular_file_bytes(context_path, reject_symlink_parents=True) != context_bytes):
            raise ValueError("SDK iOS package original execution capture changed before publication")
        if (read_regular_file_bytes(Path(plan), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(retained_plan, reject_symlink_parents=True) != plan_bytes):
            raise ValueError("SDK iOS package original plan changed before publication")
        publish_regular_tree(candidate, destination / "shard")
    return finalized


def main(argv=None) -> int:
    from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in (
        "plan", "destination", "keyring", "keys-directory",
        "developer-directory", "tooling-evidence", "tooling-public-key",
        "java-executable", "repository-root",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    parser.add_argument("--expected-build-key", required=True)
    parser.add_argument("--sdk-inputs-artifact-id", type=int, required=True)
    parser.add_argument("--sdk-inputs-artifact-sha256", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--policy-revision", required=True)
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    parser.add_argument("--tooling-keyring", type=Path)
    parser.add_argument("--tooling-keys-directory", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    add_completed_frozen_argument(parser)
    parser.add_argument("--retained-sdk-inputs-source", type=Path, default=argparse.SUPPRESS)
    arguments = vars(parser.parse_args(argv))
    if (arguments["tooling_keyring"] is None) != (arguments["tooling_keys_directory"] is None):
        parser.error("Apple tooling keyring and keys directory must be supplied together")
    try:
        if "retained_sdk_inputs_source" in arguments:
            arguments["retained_sdk_inputs_source"] = product_reuse._canonical_control(
                arguments["retained_sdk_inputs_source"], "Caller retained SDK input source")
        with metadata_admission_options(arguments) as admissions, completed_frozen_options(arguments) as semantic:
            apple_policy = arguments.pop("sdk_apple_validation_policy")
            if apple_policy is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(
                    apple_policy, "Caller Apple validation policy")
            execute(**arguments, environ=os.environ,
                    token=os.environ.get("GITHUB_TOKEN", ""), **admissions, **semantic)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
