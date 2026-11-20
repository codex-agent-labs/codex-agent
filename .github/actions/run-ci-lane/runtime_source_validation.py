"""Fixed full Runtime source tests from native-qualified retained executables.

The caller keeps its existing verified-state/session owners open, and publishes
the three detached controls only after those owners exit. This is not a phase V
receipt, and does not cover Wasm or the separate build-logic source fixtures.
"""
from contextlib import ExitStack
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ci"))

import product_reuse as products
from native_wrappers import HOSTS, host_classifier
from products.inventory import (canonical_json_bytes, git_file_inventory, git_inventory,
    git_inventory_paths, load_json_bytes, read_regular_file_bytes,
    sha256_bytes, require_regular_directory)
from products.registry import PhaseInstanceId
from products.restore import memoized_file_inventory
from reuse_qualification import CompletedFrozenReuse
from runtime_reference_archive import (open_reference_archive, open_stored_reference_archive,
    copy_reference_member)
from products.signing_isolation import require_no_signing_secret

_SOURCE = "codex-agent-runtime-desktop/src/"
_TARGETS = {"linux-x64": "linuxX64", "macos-x64": "macosX64", "windows-x64": "mingwX64"}
_FIELDS = ("product", "component", "phase", "target", "buildKey", "receiptSha256", "objectSha256")
_LIMIT = 1024 * 1024


def _source_inventory(receipt, root, revision):
    sets = ("commonTest", "desktopTest", "nativeTest")
    prefixes = tuple(_SOURCE + value + "/" for value in sets)
    original = [row for row in receipt["inputs"]["inventory"]
                if row["relativePath"].startswith(prefixes)]
    paths = sorted(git_inventory_paths(git_inventory(root, revision, tuple(p + "*" for p in prefixes))))
    if (not original or paths != [row["relativePath"] for row in original]
            or git_file_inventory(root, revision, paths) != original):
        raise ValueError("Retained test executable does not cover the exact current source set/bytes")
    return original


def _native_listing(raw):
    suite, tests = None, []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        if re.fullmatch(r"[\w.]+\.", line):
            suite = line[:-1]
        elif suite is not None and re.fullmatch(r"  [\w]+", line):
            tests.append(suite + "." + line.strip())
        else:
            raise ValueError("Unexpected complete native discovery format")
    if not tests or len(tests) != len(set(tests)):
        raise ValueError("Native discovery is empty or ambiguous")
    return tests


def _copy_outputs(state, instance, kinds, destination, stack, workflow, token):
    native = state.completed_frozen
    record = state.prior_by_instance[instance]
    envelope = native.envelope(record)
    sources = [row for row in native.runtime_sources()
               if products._identity(row["receipt"]) == instance]
    if envelope is None or len(sources) != 1 or sources[0]["receipt"] != envelope["receipt"]:
        raise ValueError("Retained source test lacks its exact native original")
    artifact, _, observed, original_workflow = products._authenticate_runtime_original_reference_source(
        state.plan, state.consumer["producer"], sources[0], trusted_workflow_sha=workflow, token=token)
    jobs = products._matching_ci_jobs(observed[0]["jobs"],
        f"product-validation / runtime-{instance.component}-{instance.phase}-{instance.target}")
    if len(jobs) != 1:
        raise ValueError("Retained source-test original job is missing or ambiguous")
    locator = products._runtime_original_locator(artifact, original_workflow, instance, jobs[0])
    members = native.original_files(locator, envelope["receipt"])
    objects = [row for row in members if row["sha256"] == record["objectSha256"]]
    if len(objects) != 1:
        raise ValueError("Retained source-test object member is missing or ambiguous")
    archive, stream = stack.enter_context(open_reference_archive(artifact, token))
    nested = stack.enter_context(open_stored_reference_archive(archive,
        objects[0]["relativePath"], expected_bytes=objects[0]["bytes"]))
    outputs = [row for row in envelope["receipt"]["outputs"] if row["kind"] in kinds]
    if len(outputs) != len(kinds) or {row["kind"] for row in outputs} != set(kinds):
        raise ValueError("Retained source tests require one exact output per selected kind")
    for row in outputs:
        copy_reference_member(nested, "stage/" + row["relativePath"], destination / row["relativePath"], row)
    if stream is not None:
        products.count("retainedSourceTestRangeBytes", stream.transferred)
    products.count("retainedSourceTestLogicalBytes", sum(row["bytes"] for row in outputs))
    return envelope, {row["kind"]: row for row in outputs}


def run_retained_native_tests(state, *, target, plan_path,
                                      repository_root, environ, trusted_workflow_sha):
    """Run a fixed complete suite under the caller's existing live state owner."""
    if target not in _TARGETS:
        raise ValueError("Unsupported native source-test target")
    if type(state) is not products._VerifiedProductState or type(state.completed_frozen) is not CompletedFrozenReuse:
        raise ValueError("Source tests require concrete live native state authority")
    if not isinstance(trusted_workflow_sha, str) or re.fullmatch(r"[0-9a-f]{40}", trusted_workflow_sha) is None:
        raise ValueError("Source tests require the exact current workflow pin")
    root, plan_path = Path(repository_root).resolve(strict=True), Path(plan_path)
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=4 * _LIMIT, reject_symlink_parents=True)
    lane = "desktop-" + target
    if (load_json_bytes(plan_bytes) != state.plan or state.consumer != products._consumer(state.plan, environ)
            or state.plan["lanes"].get(lane, {}).get("test") is not True
            or environ.get("CI_VALIDATION_COMMIT") != state.plan["validationCommit"]
            or environ.get("CI_VALIDATION_TREE") != state.plan["validationTree"]):
        raise ValueError("Source tests differ from the authorized current source/lane")
    if host_classifier() != target or HOSTS[target][2:4] != (environ.get("RUNNER_OS"), environ.get("RUNNER_ARCH")):
        raise ValueError("Source tests must execute on the exact target host")
    require_no_signing_secret(environ)
    native = state.completed_frozen
    native.check_consumer(state.consumer)
    binary = PhaseInstanceId("runtime", target, "binary", target)
    package = PhaseInstanceId("runtime", target, "package", target)
    instances = (binary, package)
    for instance in instances:
        row, carrier = state.prior_by_instance.get(instance), state.prior_carrier_phases.get(instance)
        if row is None or carrier is None or row["state"] not in {"retained", "reused"} or any(row[k] != carrier[k] for k in _FIELDS):
            raise ValueError("Source tests lack an exact retained predecessor")
    originals = [{k: state.prior_by_instance[i][k] for k in _FIELDS} for i in instances]
    binary_envelope = native.envelope(state.prior_by_instance[binary])
    if binary_envelope is None:
        raise ValueError("Source tests lack the original binary input inventory")
    inventory = _source_inventory(binary_envelope["receipt"], root, state.plan["validationCommit"])
    failure = root / "build/ci/retained-source-tests" / ("native-" + target) / "failure.log"
    if failure.exists() or failure.is_symlink():
        raise ValueError("Source-test diagnostics must be fresh")
    def retain_failure(raw):
        failure.parent.mkdir(parents=True, exist_ok=True)
        require_regular_directory(failure.parent, "Source-test diagnostic parent")
        with failure.open("xb") as output:
            output.write(raw)

    with tempfile.TemporaryDirectory(prefix="retained-source-tests-") as temporary, ExitStack() as stack:
        private = Path(temporary).resolve()
        inputs = private / "inputs"
        inputs.mkdir()
        token = environ.get("GITHUB_TOKEN", "")
        native_kinds = ("app-server", "validation-runner")
        _, platform_outputs = _copy_outputs(state, package, native_kinds,
            inputs / "native", stack, trusted_workflow_sha, token)
        runtime_observation = {"host": target, "runnerOs": HOSTS[target][2], "runnerArch": HOSTS[target][3]}
        runner_output = platform_outputs["validation-runner"]
        if runner_output not in binary_envelope["receipt"]["outputs"]:
            raise ValueError("Native package changed its original complete test executable")
        executable = inputs / "native" / runner_output["relativePath"]
        executable.chmod(0o700)
        environment = products._worker_process_environment(root, state.producer, private, environ)
        for name in ("GITHUB_TOKEN", "GH_TOKEN", "REUSE_AUTHORITY_READ_TOKEN", "CLASSPATH"):
            environment.pop(name, None)
        for name in ("data", "workspace", "tmp"):
            (private / name).mkdir()
        environment.update({"CODEX_AGENT_RUNTIME_BUNDLE_DIRECTORY": str(inputs / "native/outputs/app-server"),
            "CODEX_AGENT_RUNTIME_DATA_DIRECTORY": str(private / "data"), "CODEX_AGENT_WORKSPACE": str(private / "workspace"),
            "CODEX_HOME": str(private / "data"), "CODEX_SQLITE_HOME": str(private / "data"),
            "CODEX_AGENT_DESKTOP_TARGET": _TARGETS[target]})
        environment.update(dict.fromkeys(("TMPDIR", "TMP", "TEMP"), str(private / "tmp")))
        before = memoized_file_inventory(inputs)

        def unchanged():
            require_no_signing_secret(environ)
            native.check_consumer(state.consumer)
            products._runtime_worker_checkout(root, state.producer)
            if (read_regular_file_bytes(plan_path, max_bytes=4 * _LIMIT, reject_symlink_parents=True) != plan_bytes
                    or memoized_file_inventory(inputs) != before or native.envelope(state.prior_by_instance[binary]) != binary_envelope):
                raise ValueError("Retained source-test input changed during execution")

        def run(command, name):
            log = private / (name + ".log")
            started = time.perf_counter_ns()
            try:
                unchanged()
                with log.open("xb") as output:
                    result = subprocess.run(command, cwd=private, env=environment, stdin=subprocess.DEVNULL,
                        stdout=output, stderr=subprocess.STDOUT, timeout=900, check=False)
                raw = read_regular_file_bytes(log, max_bytes=_LIMIT, reject_symlink_parents=True)
                if result.returncode:
                    raise ValueError(f"Retained source-test command failed: {name} ({result.returncode})")
                return raw, time.perf_counter_ns() - started
            except BaseException:
                if log.is_file() and not failure.exists():
                    retain_failure(read_regular_file_bytes(log, max_bytes=_LIMIT, reject_symlink_parents=True))
                raise
            finally:
                try:
                    unchanged()
                except BaseException:
                    if log.is_file() and not failure.exists():
                        retain_failure(read_regular_file_bytes(log, max_bytes=_LIMIT, reject_symlink_parents=True))
                    raise

        discovery, _ = run([str(executable), "--ktest_list_tests"], "discovery")
        try:
            listed = _native_listing(discovery)
        except ValueError:
            retain_failure(discovery)
            raise
        # No filter, ignored-test override or product evidence-entrypoint selection.
        command = [str(executable), "--ktest_logger=GTEST"]
        execution, elapsed = run(command, "tests")
        passed = re.findall(rb"(?m)^\[  PASSED  \] (\d+) tests?\.\r?$", execution)
        if passed != [str(len(listed)).encode("ascii")]:
            retain_failure(execution)
            raise ValueError("Full native run must pass every discovered test")
        selection = {"unfiltered": True, "discoveredTests": listed, "passedTests": len(listed)}
        unchanged()
        stack.close()
        record = {"schemaVersion": 1, "kind": "retained-runtime-source-tests", "result": "passed",
            "producer": state.consumer["producer"], "planSha256": sha256_bytes(plan_bytes), "component": "native",
            "target": target, "lane": lane, "originalInputs": originals, "sourceInventory": inventory, "selection": selection,
            "runtimeObservation": runtime_observation,
            "executionElapsedNs": elapsed, "discoverySha256": sha256_bytes(discovery), "executionSha256": sha256_bytes(execution)}
        controls = {"retained-source-tests.json": canonical_json_bytes(record),
                    "discovery.log": discovery, "execution.log": execution}
        if sum(map(len, controls.values())) > _LIMIT - 4096:
            raise ValueError("Retained source-test controls exceed their bounded upload contract")
        return controls


def selected_native_source_targets(plan, enabled):
    if type(enabled) is not bool:
        raise ValueError("Native source-test routing must be an explicit boolean")
    if not enabled:
        return ()
    selected = []
    for target in _TARGETS:
        value = plan["lanes"]["desktop-" + target]["test"]
        if type(value) is not bool:
            raise ValueError("Native source-test selection must be boolean")
        if value:
            selected.append(target)
    if not selected:
        raise ValueError("Native source-test routing requires a selected fixed host")
    return tuple(selected)


def _native_merge_inputs(native, consumer, root, target):
    """Retain native/adapter validation duties separately from fresh source tests."""
    from products.registry import phase_instance_dependencies
    from products.restore import PHASE_PLAN_KEYS
    if type(native) is not CompletedFrozenReuse:
        raise ValueError("Native source gate requires live native semantic authority")
    native.check_consumer(consumer)
    _, records = native._values()
    binary = PhaseInstanceId("runtime", target, "binary", target)
    package = PhaseInstanceId("runtime", target, "package", target)
    validations = tuple(PhaseInstanceId("runtime", component, "validation", target)
                        for component in (target, "jvm", "node-js", "node-wasm"))

    def envelope(identity):
        record = records.get(identity)
        result = None if record is None else native.envelope(record)
        if result is None:
            raise ValueError("Native source gate lacks an exact current-eligible Runtime original")
        return result

    binary_envelope, package_envelope = envelope(binary), envelope(package)
    runner = [row for row in package_envelope["receipt"]["outputs"] if row["kind"] == "validation-runner"]
    if len(runner) != 1 or runner[0] not in binary_envelope["receipt"]["outputs"]:
        raise ValueError("Native package changed its original complete test executable")
    versions = products._versions(root, consumer["producer"]["commit"])
    retained = []
    for identity in validations:
        original = envelope(identity)
        inputs = original["receipt"]["inputs"]
        current = native.phase_plan(identity, {
            "inventory": inputs["inventory"], "versions": versions,
            "toolchain_profile_digest": inputs["toolchainProfileDigest"],
            "flags_digest": inputs["flagsDigest"], "output_schema_version": inputs["outputSchemaVersion"]},
            original, [envelope(parent) for parent in phase_instance_dependencies(identity)])
        if current != {key: original["receipt"][key] for key in PHASE_PLAN_KEYS}:
            raise ValueError("Native source gate changes a retained Runtime validation dependency")
        retained.append({**{key: records[identity][key] for key in _FIELDS},
                         "originalProducer": original["receipt"]["producer"]})
    return {
        "originalInputs": [{key: records[identity][key] for key in _FIELDS} for identity in (binary, package)],
        "sourceInventory": _source_inventory(binary_envelope["receipt"], root, consumer["producer"]["commit"]),
        "retainedRuntimeValidations": retained,
    }


def _validate_native_source_controls(members, producer, plan_sha256, target, expected):
    from products.inventory import load_canonical_json_bytes, require_integer
    if set(members) != {"retained-source-tests.json", "discovery.log", "execution.log"}:
        raise ValueError("Native source upload must contain exactly its three controls")
    record = load_canonical_json_bytes(members["retained-source-tests.json"])
    listed = _native_listing(members["discovery.log"])
    passed = re.findall(rb"(?m)^\[  PASSED  \] (\d+) tests?\.\r?$", members["execution.log"])
    if passed != [str(len(listed)).encode("ascii")]:
        raise ValueError("Native source execution does not pass the complete discovered suite")
    duration = require_integer(record.get("executionElapsedNs"), "Native source execution duration", 0)
    exact = {"schemaVersion": 1, "kind": "retained-runtime-source-tests", "result": "passed",
        "producer": producer, "planSha256": plan_sha256, "component": "native",
        "target": target, "lane": "desktop-" + target,
        "originalInputs": expected["originalInputs"], "sourceInventory": expected["sourceInventory"],
        "selection": {"unfiltered": True, "discoveredTests": listed, "passedTests": len(listed)},
        "runtimeObservation": {"host": target, "runnerOs": HOSTS[target][2], "runnerArch": HOSTS[target][3]},
        "executionElapsedNs": duration, "discoverySha256": sha256_bytes(members["discovery.log"]),
        "executionSha256": sha256_bytes(members["execution.log"])}
    # Canonical equality also rejects bool-as-int substitutions in typed fields.
    if canonical_json_bytes(record) != canonical_json_bytes(exact):
        raise ValueError("Native source controls change current source, original inputs, host or execution")
    return record


def observed_native_source_tests(native, *, plan, plan_sha256, root, consumer, observation, token):
    """Read only three bounded controls per already observed exact current job."""
    from products.inventory import require_integer, require_sha256, verified_zip_contents
    producer = consumer["producer"]
    targets = selected_native_source_targets(plan, True)
    before = {target: _native_merge_inputs(native, consumer, root, target) for target in targets}
    listing = products.paginated_items(
        f"https://api.github.com/repos/{producer['repository']}/actions/runs/{producer['runId']}/artifacts",
        "artifacts", token)
    results = {}
    for target in targets:
        name = f"codex-agent-retained-native-source-{target}-{producer['tree']}-attempt-{producer['runAttempt']}"
        matches = [row for row in listing if type(row) is dict and row.get("name") == name]
        if len(matches) != 1:
            raise ValueError("Native source upload is missing or ambiguous")
        artifact_id = require_integer(matches[0].get("id"), "Native source artifact ID", 1)
        digest = require_sha256(matches[0].get("digest"), "Native source artifact SHA")
        artifact = products._contract_ci_upload_metadata(artifact_id, digest, name, producer, observation["run"], token)
        job = "product-validation / retained-native-source / retained-native-" + target
        products._require_artifact_job_window(observation, job, artifact)
        size = require_integer(artifact["size_in_bytes"], "Native source upload bytes", 1)
        if size > _LIMIT:
            raise ValueError("Native source upload exceeds its control-only bound")
        names = ("retained-source-tests.json", "discovery.log", "execution.log")
        with tempfile.TemporaryDirectory(prefix="native-source-controls-") as temporary:
            archive = Path(temporary).resolve() / "controls.zip"
            products._reuse_contract_ci_upload(artifact, producer, observation["run"], token,
                destination=archive, limit=_LIMIT, artifact_sha256=digest, size=size)
            inventory, members, transport = verified_zip_contents(archive,
                max_archive_bytes=_LIMIT, max_members=3, max_entry_bytes=_LIMIT,
                max_total_bytes=_LIMIT, retained_paths=names, max_retained_bytes=_LIMIT, require_sorted=False)
            if transport != {"bytes": size, "sha256": digest} or {row["relativePath"] for row in inventory} != set(names):
                raise ValueError("Native source upload differs from its authenticated three-control closure")
            record = _validate_native_source_controls(members, producer, plan_sha256, target, before[target])
        results["desktop-" + target] = {"artifactId": artifact_id, "artifactSha256": digest,
            "recordSha256": sha256_bytes(members["retained-source-tests.json"]), "original": record,
            "retainedRuntimeValidations": before[target]["retainedRuntimeValidations"]}
    if {target: _native_merge_inputs(native, consumer, root, target) for target in targets} != before:
        raise ValueError("Native source authority or current source changed during observation")
    return results


def main(argv=None):
    """Run a selected native suite from the current protected product-resume upload."""
    import argparse
    from products.inventory import publish_regular_tree
    from products.restore import verification_session
    from reuse_qualification import completed_frozen_options

    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--target", choices=tuple(_TARGETS), required=True)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--completed-frozen-policy", required=True, type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    args.repository_root = root
    build = require_regular_directory(root / "build", "CI build directory")
    destination = build / "ci/retained-source-tests" / ("native-" + args.target) / "controls"
    plan = products._validate_plan(args.plan, root)
    if not products.validate_remote_build_authorization(plan)[0] or plan["mergeReady"] is not True:
        raise ValueError("Source tests require the current authorized CI plan")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Source-test controls must be fresh")

    controls = {}

    def consume(state):
        if controls:
            raise ValueError("Source-test inputs already consumed")
        controls.update(run_retained_native_tests(state, target=args.target,
            plan_path=args.plan, repository_root=root, environ=os.environ,
            trusted_workflow_sha=args.trusted_workflow_sha))

    # Source-test controls outlive the authenticated capability only after all owner checks pass.
    with tempfile.TemporaryDirectory(prefix="retained-native-", dir=build) as work:
        capture = Path(work) / "capture"
        with verification_session(), products._ci_observation_batch(
                (os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]), share_nested=True), \
                completed_frozen_options(args) as completed:
            products.capture_runtime_resume_upload(args.plan, capture, artifact_id=args.artifact_id,
                artifact_sha256=args.artifact_sha256, trusted_workflow_sha=args.trusted_workflow_sha,
                repository_root=root, environ=os.environ, token=os.environ["GITHUB_TOKEN"],
                state_wave=0, allow_earlier_attempt=True, **completed)
            original = capture / "original"
            captured_plan = original / "product-resume-inputs/plan/impact-plan.json"
            if read_regular_file_bytes(captured_plan, max_bytes=4 * _LIMIT, reject_symlink_parents=True) != \
                    read_regular_file_bytes(args.plan, max_bytes=4 * _LIMIT, reject_symlink_parents=True):
                raise ValueError("Captured source-test plan differs from the current plan")
            products.inspect_products(captured_plan, original / "product-resume-state", repository_root=root,
                environ=os.environ, sdk_original_workflow_sha=args.trusted_workflow_sha,
                _verified_state_consumer=consume, **completed)
        if controls.keys() != {"retained-source-tests.json", "discovery.log", "execution.log"}:
            raise ValueError("Incomplete retained native source-test controls")
        stage = Path(work) / "controls"
        stage.mkdir()
        for name, raw in controls.items():
            (stage / name).write_bytes(raw)
        publish_regular_tree(stage, destination)


if __name__ == "__main__":
    main()
