"""Recover official Android validation coordinates for elected fresh metadata.

The captured wave state and caller policies must already be authenticated by
the enclosing caller. This returns transport coordinates, not Firebase or
metadata admission; the original reader must still replay those gates.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (canonical_json_bytes, regular_file_inventory,
    require_exact_keys, require_integer, require_sha256, sha256_bytes)
from products.plan import _upstream_record
from products.receipt import validate_phase_receipt, validate_producer
from products.registry import PhaseInstanceId
from products.restore import restore_object
from products.signing_isolation import require_no_signing_secret
from reuse import github_output
from sdk_android_original_upload_locator import locate_sdk_android_validation_upload
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options


_VALIDATION = PhaseInstanceId("sdk", "sdk-android", "validation", "android")
_METADATA = PhaseInstanceId("sdk", "sdk-android", "metadata", "android")
_COORDINATES = ("validation_receipt_sha256", "validation_artifact_id",
                "validation_artifact_sha256", "validation_run_id",
                "validation_run_attempt")


def _fresh_coordinates(value):
    value = require_exact_keys(value, _COORDINATES, "Fresh Android validation coordinates")
    for name in ("validation_receipt_sha256", "validation_artifact_sha256"):
        require_sha256(value[name], "Fresh " + name)
    for name in ("validation_artifact_id", "validation_run_id", "validation_run_attempt"):
        require_integer(value[name], "Fresh " + name, minimum=1)
    return value


def validation_handoff(plan, discovery, state, *, expected_metadata_build_key,
        trusted_workflow_sha, repository_root, environ=None, token,
        sdk_validation_tooling=None, sdk_apple_validation_policy=None,
        sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
        fresh_validation=None, github_output_path=None):
    """Select one immutable validation object and observe its official upload."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if environment is not os.environ:
        require_no_signing_secret(os.environ)
    expected_metadata_build_key = require_sha256(
        expected_metadata_build_key, "Elected Android metadata build key")
    if fresh_validation is not None:
        fresh_validation = _fresh_coordinates(fresh_validation)
    root = Path(repository_root).resolve(strict=True)
    if github_output_path is not None:
        github_output_path = Path(github_output_path).absolute()
        if (github_output_path.resolve(strict=True) != github_output_path
                or root == github_output_path or root in github_output_path.parents):
            raise ValueError("Android handoff output must be an existing non-symbolic runner file outside the repository")
    plan = Path(plan).absolute()
    discovery, state, _ = product_reuse._product_materialization_paths(
        root, discovery, state, root / "build/android-validation-handoff-unused")
    plan_bytes = product_reuse.read_regular_file_bytes(plan, reject_symlink_parents=True)
    before = {path: regular_file_inventory(path, allow_empty=True)
              for path in (discovery, state)}
    commit = product_reuse._git_value(root, "rev-parse", "HEAD^{commit}")
    tree = product_reuse._git_value(root, "rev-parse", "HEAD^{tree}")

    def unchanged():
        require_no_signing_secret(environment)
        if environment is not os.environ:
            require_no_signing_secret(os.environ)
        if (product_reuse.read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_bytes
                or any(regular_file_inventory(path, allow_empty=True) != before[path]
                       for path in before)
                or product_reuse._git_value(root, "rev-parse", "HEAD^{commit}") != commit
                or product_reuse._git_value(root, "rev-parse", "HEAD^{tree}") != tree):
            raise ValueError("Android validation handoff inputs changed during official lookup")

    try:
        verified = product_reuse._verified_product_state(
            plan, discovery, state, root, environment, sdk_validation_tooling,
            sdk_original_workflow_sha=trusted_workflow_sha,
            sdk_apple_validation_policy=sdk_apple_validation_policy,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission)
        ready = verified.prior_ready_plans.get(_METADATA)
        phase = verified.prior_by_instance.get(_VALIDATION)
        if (verified.plan["validationCommit"] != commit
                or verified.plan["validationTree"] != tree
                or ready is None or ready["buildKey"] != expected_metadata_build_key
                or _METADATA in verified.sources or phase is None
                or phase["state"] not in {"retained", "reused"}
                or _VALIDATION not in verified.sources
                or _VALIDATION not in verified.prior_carrier_phases):
            raise ValueError("Android metadata lacks an elected retained validation predecessor")
        record = verified.prior_carrier_phases[_VALIDATION]
        if any(record[name] != phase[name] for name in
               ("buildKey", "receiptSha256", "objectSha256")):
            raise ValueError("Android validation carrier differs from its elected object")
        with tempfile.TemporaryDirectory(prefix="android-validation-handoff-") as temporary:
            private = Path(temporary).resolve()
            restored = restore_object(
                verified.sources[_VALIDATION], private / "stage",
                build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                object_sha256=record["objectSha256"])
            raw = restored["receiptBytes"]
            receipt = validate_phase_receipt(restored["receipt"])
            if (sha256_bytes(raw) != record["receiptSha256"]
                    or canonical_json_bytes(receipt) != raw
                    or tuple(receipt[name] for name in
                        ("product", "component", "phase", "target")) !=
                       ("sdk", "sdk-android", "validation", "android")
                    or receipt["buildKey"] != record["buildKey"]
                    or _upstream_record(receipt) not in ready["inputs"]["upstreamArtifacts"]):
                raise ValueError("Android validation object differs from metadata's exact upstream")
            producer = validate_producer(receipt["producer"], "Original Android validation producer")
            selected = private / "validation-receipt.json"
            selected.write_bytes(raw)
            unchanged()
            located = locate_sdk_android_validation_upload(
                plan, selected, expected_receipt_sha256=record["receiptSha256"],
                trusted_workflow_sha=trusted_workflow_sha, repository_root=root,
                environ=environment, token=token)
            result = {
                "validation_receipt_sha256": record["receiptSha256"],
                "validation_artifact_id": located["artifact_id"],
                "validation_artifact_sha256": located["artifact_sha256"],
                "validation_run_id": producer["runId"],
                "validation_run_attempt": producer["runAttempt"],
            }
            if fresh_validation is not None and result != fresh_validation:
                raise ValueError("Fresh Android validation coordinates differ from elected original")
            result["validation_original_mode"] = (
                "fresh" if fresh_validation is not None else "retained")
            unchanged()
            if selected.read_bytes() != raw:
                raise ValueError("Selected Android validation receipt changed during lookup")
            github_output(github_output_path, {
                name.replace("_", "-"): value for name, value in result.items()})
            unchanged()
            return result
    finally:
        unchanged()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-metadata-build-key", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--sdk-validation-tooling", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    parser.add_argument("--github-output", type=Path, required=True)
    for name in _COORDINATES:
        parser.add_argument("--expected-" + name.replace("_", "-"))
    add_metadata_admission_arguments(parser)
    args = vars(parser.parse_args(argv))
    output = args.pop("github_output")
    args["github_output_path"] = output
    expected = {name: args.pop("expected_" + name) for name in _COORDINATES}
    if any(value is not None for value in expected.values()):
        if any(value is None for value in expected.values()):
            parser.error("Fresh Android validation coordinates must be supplied together")
        for name in ("validation_artifact_id", "validation_run_id", "validation_run_attempt"):
            try:
                expected[name] = int(expected[name])
            except ValueError:
                parser.error("Expected " + name.replace("_", "-") + " must be an integer")
        args["fresh_validation"] = expected
    args["discovery"] = args.pop("discovery_root")
    args["state"] = args.pop("state_root")
    for name in ("sdk_validation_tooling", "sdk_apple_validation_policy"):
        if args[name] is not None:
            args[name] = product_reuse._canonical_control(args[name], "Caller Android " + name)
    try:
        with metadata_admission_options(args) as admissions:
            validation_handoff(
                **args, **admissions, environ=os.environ, token=os.environ["GITHUB_TOKEN"])
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
