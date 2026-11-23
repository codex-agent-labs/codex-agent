"""Stage the original SDK iOS binary frameworks for the unchanged hosted ios-package lane.

Retained ordinary Apple mode builds no framework lane. The ios-package lane still
runs every one of its own build/metadata tasks through ``ci/run-lane.sh`` and
emits its own strict receipt; this helper only supplies that lane's two framework
inputs. They are the eight framework leaves of the current qualified SDK iOS
binary original (the bytes the native SDK iOS package phase packages), streamed
from the authenticated original upload and checked leaf by leaf against that
original's receipt. It never compiles, never writes a lane receipt and grants no
lane waiver. Publish only after every native/state owner has exited.
"""
from contextlib import ExitStack
from pathlib import Path
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ci"))
import product_reuse as products
from completed_sdk_reuse import original_worker_member
from native_wrappers import host_classifier
from products.inventory import (canonical_json_bytes, load_canonical_json_bytes, load_json_bytes,
    publish_regular_tree, read_regular_file_bytes, sha256_bytes)
from products.registry import PhaseInstanceId
from products.restore import _VERIFICATION_SESSION, memoized_file_inventory, verification_session
from products.signing_isolation import require_no_signing_secret
from reuse_qualification import CompletedFrozenReuse
from runtime_reference_archive import open_reference_archive, open_stored_reference_archive, copy_reference_member
from sdk_android_evidence_capture import _retained_dependency_plan

_BINARY = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
_FIELDS = ("product", "component", "phase", "target", "buildKey", "receiptSha256", "objectSha256")
_TARGETS = {"device": "ios-arm64", "simulator": "ios-simulator-arm64"}
_LEAVES = ("CodexAgent", "Headers/CodexAgent.h", "Info.plist", "Modules/module.modulemap")
_LANE = "ios-package"
_ACTIONS = frozenset(("build", "metadata"))
_JOB = "retained-package"
_RECORD = "retained-apple-package-inputs.json"
_LIMIT = 16 * 1024 * 1024
DESTINATION = Path("build/ci/retained-package")


def _prefix(target):
    return f"outputs/apple-binary/{target}/CodexAgent.framework/"


def selected_actions(plan):
    """The ordinary lane duties this route serves; any other action is unmatched."""
    row = plan["lanes"][_LANE]
    if type(row) is not dict or any(type(row.get(key)) is not bool for key in ("build", "test", "metadata")):
        raise ValueError("Apple package lane selection must be boolean")
    actual = {key for key in ("build", "test", "metadata") if row[key]}
    if not actual or actual - _ACTIONS:
        raise ValueError("Retained Apple package inputs serve only the selected ios-package build/metadata duties")
    return sorted(actual)


def _expected(native, consumer):
    if type(native) is not CompletedFrozenReuse:
        raise ValueError("Apple package inputs require concrete native authority")
    native.check_consumer(consumer)
    _, records = native._values()
    record = records.get(_BINARY)
    envelope = None if record is None else native.envelope(record)
    if envelope is None:
        raise ValueError("Apple package inputs require the current-eligible SDK iOS binary")
    frameworks = {}
    for name, target in _TARGETS.items():
        prefix = _prefix(target)
        rows = [r for r in envelope["receipt"]["outputs"] if r["relativePath"].startswith(prefix)]
        if (len(rows) != len(_LEAVES) or {r["relativePath"][len(prefix):] for r in rows} != set(_LEAVES)
                or any(r["kind"] != "apple-binary" for r in rows)):
            raise ValueError("Apple package inputs require exactly the four original leaves per framework")
        frameworks[name] = sorted(rows, key=lambda r: r["relativePath"])
    return {"originalInput": {k: record[k] for k in _FIELDS}, "frameworks": frameworks}


def _framework_inventory(expected, name):
    prefix = _prefix(_TARGETS[name])
    return sorted(({"relativePath": r["relativePath"][len(prefix):], "bytes": r["bytes"], "sha256": r["sha256"]}
                   for r in expected["frameworks"][name]), key=lambda r: r["relativePath"])


def _copy_frameworks(state, record, expected, destination, stack, token):
    """Stream only the eight receipt-bound leaves from the one authenticated original."""
    native = state.completed_frozen
    envelope = native.envelope(record)
    _retained_dependency_plan(state, _BINARY, envelope)
    extension = native.sdk_extension()
    if extension is not None and any(products._identity(row) == _BINARY
                                    for row in extension["spec"]["completedPhases"]):
        if not original_worker_member(extension["spec"]):
            raise ValueError("Apple package frameworks require the qualified original worker member")
        members = [r for r in extension["proof"]["members"] if r["sha256"] == record["objectSha256"]]
        if len(members) != 1:
            raise ValueError("Apple package binary object is absent or ambiguous")
        member = members[0]
        _, artifact, _ = native.observe_extended_sdk(record, producer=state.producer, token=token)
    else:
        original = native.sdk_original()
        if original is None or original["proof"]["member"]["sha256"] != record["objectSha256"]:
            raise ValueError("Apple package binary object differs from its native parent")
        member = original["proof"]["member"]
        artifact, _, _ = native.observe_sdk(plan=state.plan, producer=state.producer, token=token)
    archive, _ = stack.enter_context(open_reference_archive(
        artifact, token, **products._worker_upload_reference_limits(_BINARY)))
    nested = stack.enter_context(open_stored_reference_archive(archive,
        member["relativePath"], expected_bytes=member["bytes"]))
    for name, target in _TARGETS.items():
        prefix = _prefix(target)
        for row in expected["frameworks"][name]:
            copy_reference_member(nested, "stage/" + row["relativePath"],
                destination / name / "CodexAgent.framework" / row["relativePath"][len(prefix):], row)

    def unchanged():
        if native.envelope(record) != envelope:
            raise ValueError("Apple package framework authority changed during use")
    stack.callback(unchanged)


def stage_retained_package_inputs(state, *, plan_path, repository_root, environ, staging):
    """Copy and check the frameworks inside the live verified state; publish nothing."""
    require_no_signing_secret(environ)
    session = _VERIFICATION_SESSION.get()
    if session is None or type(state) is not products._VerifiedProductState:
        raise ValueError("Apple package inputs require the existing live verified state")
    root, plan_path = Path(repository_root).resolve(strict=True), Path(plan_path)
    plan_raw = read_regular_file_bytes(plan_path, max_bytes=_LIMIT, reject_symlink_parents=True)
    if (load_json_bytes(plan_raw) != state.plan or products._consumer(state.plan, environ) != state.consumer
            or environ.get("GITHUB_ACTIONS") != "true" or environ.get("GITHUB_JOB") != _JOB
            or environ.get("CI_VALIDATION_COMMIT") != state.plan["validationCommit"]
            or environ.get("CI_VALIDATION_TREE") != state.plan["validationTree"]
            or host_classifier() != "macos-arm64" or (environ.get("RUNNER_OS"), environ.get("RUNNER_ARCH")) != ("macOS", "ARM64")):
        raise ValueError("Apple package inputs require the current selected Apple Silicon host")
    actions = selected_actions(state.plan)
    native = state.completed_frozen
    before = _expected(native, state.consumer)
    record = state.prior_by_instance.get(_BINARY)
    if record is None or record["state"] not in {"retained", "reused"} or {k: record[k] for k in _FIELDS} != before["originalInput"]:
        raise ValueError("Apple package state changes its original binary")
    staging = Path(staging)
    if staging.exists() or staging.is_symlink():
        raise ValueError("Apple package framework staging must be fresh")
    with ExitStack() as stack:
        products._runtime_worker_checkout(root, state.producer)
        native.check_request(state.rebased_request)
        _copy_frameworks(state, record, before, staging, stack, environ["GITHUB_TOKEN"])
        for name in _TARGETS:
            if memoized_file_inventory(staging / name / "CodexAgent.framework") != _framework_inventory(before, name):
                raise ValueError("Apple package framework differs from its consumed original leaves")
        native.check_request(state.rebased_request)
        if (_VERIFICATION_SESSION.get() is not session or _expected(native, state.consumer) != before
                or read_regular_file_bytes(plan_path, reject_symlink_parents=True) != plan_raw
                or products._consumer(state.plan, environ) != state.consumer):
            raise ValueError("Apple package inputs changed or outlived their owners")
        stack.close()
    result = {"schemaVersion": 1, "kind": "retained-apple-package-inputs", "lane": _LANE, "actions": actions,
              "producer": state.consumer["producer"], "planSha256": sha256_bytes(plan_raw), **before,
              "laneReceipt": "unchanged-hosted-ios-package-lane", "productBodiesCompiled": False}
    return load_canonical_json_bytes(canonical_json_bytes(validate_record(result, state.consumer["producer"],
                                                                         sha256_bytes(plan_raw), before)))


def validate_record(value, producer, plan_sha256, expected):
    """Exact detached control: it never substitutes the lane's own receipt."""
    exact = {"schemaVersion": 1, "kind": "retained-apple-package-inputs", "lane": _LANE,
             "actions": value.get("actions"), "producer": producer, "planSha256": plan_sha256, **expected,
             "laneReceipt": "unchanged-hosted-ios-package-lane", "productBodiesCompiled": False}
    if (type(value.get("actions")) is not list or not value["actions"] or value["actions"] != sorted(set(value["actions"]))
            or not set(value["actions"]).issubset(_ACTIONS)
            or canonical_json_bytes(value) != canonical_json_bytes(exact)):
        raise ValueError("Apple package input control substitutes its lane, original or scope")
    return value


def main(argv=None):
    import argparse
    from reuse_qualification import completed_frozen_options
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "completed-frozen-policy"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    args.repository_root = root
    require_no_signing_secret(os.environ)
    plan = products._validate_plan(args.plan, root)
    if not products.validate_remote_build_authorization(plan)[0] or plan["mergeReady"] is not True:
        raise ValueError("Apple package input job is not authorized by the current plan")
    selected_actions(plan)
    destination = root / DESTINATION
    if destination.exists() or destination.is_symlink():
        raise ValueError("Apple package inputs must be fresh")
    controls = {}
    with tempfile.TemporaryDirectory(prefix="retained-package-", dir=root / "build") as tmp:
        stage = Path(tmp) / "stage"

        def consume(state):
            if controls:
                raise ValueError("Apple package inputs already consumed")
            controls["record"] = stage_retained_package_inputs(state, plan_path=args.plan, repository_root=root,
                environ=os.environ, staging=stage / "frameworks")
        capture = Path(tmp) / "capture"
        with verification_session(), products._ci_observation_batch(
                (os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]), share_nested=True), \
                completed_frozen_options(args) as completed:
            products.capture_runtime_resume_upload(args.plan, capture, artifact_id=args.artifact_id,
                artifact_sha256=args.artifact_sha256, trusted_workflow_sha=args.trusted_workflow_sha,
                repository_root=root, environ=os.environ, token=os.environ["GITHUB_TOKEN"], state_wave=0,
                allow_earlier_attempt=True, **completed)
            original = capture / "original"
            captured_plan = original / "product-resume-inputs/plan/impact-plan.json"
            if read_regular_file_bytes(captured_plan, reject_symlink_parents=True) != read_regular_file_bytes(
                    args.plan, reject_symlink_parents=True):
                raise ValueError("Apple package captured plan changes the current plan")
            products.inspect_products(captured_plan, original / "product-resume-state", repository_root=root,
                environ=os.environ, sdk_original_workflow_sha=args.trusted_workflow_sha,
                _verified_state_consumer=consume, **completed)
        if set(controls) != {"record"}:
            raise ValueError("Apple package inputs were not produced exactly once")
        record = controls["record"]
        (stage / _RECORD).write_bytes(canonical_json_bytes(record))
        expected = [{"relativePath": _RECORD, "bytes": len(canonical_json_bytes(record)),
                     "sha256": sha256_bytes(canonical_json_bytes(record))}]
        for name in _TARGETS:
            expected += [{**row, "relativePath": f"frameworks/{name}/CodexAgent.framework/{row['relativePath']}"}
                         for row in _framework_inventory(record, name)]
        publish_regular_tree(stage, destination, expected_inventory=sorted(expected, key=lambda r: r["relativePath"]))


if __name__ == "__main__":
    main()
