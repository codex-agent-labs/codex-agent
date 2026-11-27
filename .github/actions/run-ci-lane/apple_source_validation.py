"""Compile only the current Swift simulator package/tests with the original SDK B framework.

This fixed current-source proof is distinct from canonical V and the installed KMP
consumer. Publish the three controls only after all native/state owners exit.
"""
from contextlib import ExitStack
from pathlib import Path
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ci"))
import product_reuse as products
from completed_sdk_reuse import original_worker_member
from native_wrappers import host_classifier
from products.inventory import (canonical_json_bytes, git_file_inventory, git_inventory,
    git_inventory_paths, git_regular_blob_bytes, load_canonical_json_bytes, load_json_bytes,
    read_regular_file_bytes, _open_regular_file, _stat_identity, require_exact_keys, require_integer, require_regular_directory,
    require_sha256, sha256_bytes, verified_zip_contents, publish_regular_tree)
from products.registry import PhaseInstanceId
from products.restore import _VERIFICATION_SESSION, memoized_file_inventory, verification_session
from products.signing_isolation import require_no_signing_secret
from reuse_qualification import CompletedFrozenReuse
from runtime_reference_archive import open_reference_archive, open_stored_reference_archive, copy_reference_member
from sdk_android_evidence_capture import _retained_dependency_plan

_BINARY = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
_FIELDS = ("product", "component", "phase", "target", "buildKey", "receiptSha256", "objectSha256")
_PREFIX = "outputs/apple-binary/ios-simulator-arm64/CodexAgent.framework/"
_LEAVES = ("CodexAgent", "Headers/CodexAgent.h", "Info.plist", "Modules/module.modulemap")
_TASK = ":codex-agent-runtime-ios:verifyCodexAgentSwiftSimulatorCompilation"
_LIMIT = 1024 * 1024
_SOURCE = ("codex-agent-runtime-ios/apple/Package.swift", "codex-agent-runtime-ios/apple/Sources/**",
    "codex-agent-runtime-ios/apple/Tests/**", "gradle/build-logic/src/main/kotlin/codexagent.ios-runtime.gradle.kts",
    "gradle/build-logic/src/main/kotlin/SwiftAuthenticationTestTask.kt",
    "gradle/build-logic/src/main/kotlin/ImportedAppleFrameworkTasks.kt",
    "gradle/build-logic/src/main/kotlin/IosAppleReleaseVerificationTasks.kt",
    "gradle/build-logic/src/main/kotlin/AppleDistributionFileTasks.kt")
_NAMES = ("retained-swift-source.json", "swift-simulator-compilation.json", "execution.log")


def _source(root, revision):
    paths = sorted(git_inventory_paths(git_inventory(root, revision, _SOURCE)))
    rows = git_file_inventory(root, revision, paths)
    if not rows or not any(r["relativePath"].startswith("codex-agent-runtime-ios/apple/Tests/") for r in rows):
        raise ValueError("Current Swift source inventory is incomplete")
    script = git_regular_blob_bytes(root, revision, _SOURCE[3], max_bytes=_LIMIT).decode("utf-8")
    pins = {}
    for field, name in (("xcodeVersion", "pinnedXcodeVersion"), ("xcodeBuild", "pinnedXcodeBuild"),
                        ("swiftVersion", "pinnedSwiftVersion")):
        values = re.findall(r'(?m)^private val ' + name + r' = "([^"\r\n]+)"$', script)
        if len(values) != 1:
            raise ValueError("Swift task toolchain pin is absent or ambiguous")
        pins[field] = values[0]
    return rows, pins


def _expected(native, consumer, root):
    if type(native) is not CompletedFrozenReuse:
        raise ValueError("Swift source checks require concrete native authority")
    native.check_consumer(consumer)
    _, records = native._values()
    record = records.get(_BINARY)
    envelope = None if record is None else native.envelope(record)
    if envelope is None:
        raise ValueError("Swift source checks require the current-eligible SDK iOS binary")
    selected = [r for r in envelope["receipt"]["outputs"] if r["relativePath"].startswith(_PREFIX)]
    if (len(selected) != 4 or {r["relativePath"][len(_PREFIX):] for r in selected} != set(_LEAVES)
            or any(r["kind"] != "apple-binary" for r in selected)):
        raise ValueError("Swift source check requires exactly the four original simulator framework leaves")
    source, pins = _source(root, consumer["producer"]["commit"])
    return {"originalInput": {k: record[k] for k in _FIELDS}, "frameworkFiles": selected,
            "sourceInventory": source, "toolchain": pins}


@products.measured
def _copy_framework(state, record, expected, destination, stack, token):
    native = state.completed_frozen
    envelope = native.envelope(record)
    _retained_dependency_plan(state, _BINARY, envelope)
    extension = native.sdk_extension()
    if extension is not None and any(products._identity(row) == _BINARY
                                    for row in extension["spec"]["completedPhases"]):
        if not original_worker_member(extension["spec"]):
            raise ValueError("Swift framework requires the qualified original worker member")
        members = [r for r in extension["proof"]["members"] if r["sha256"] == record["objectSha256"]]
        if len(members) != 1:
            raise ValueError("Swift binary object is absent or ambiguous")
        member = members[0]
        _, artifact, _ = native.observe_extended_sdk(record, producer=state.producer, token=token)
    else:
        original = native.sdk_original()
        if original is None or original["proof"]["member"]["sha256"] != record["objectSha256"]:
            raise ValueError("Swift binary object differs from its native parent")
        member = original["proof"]["member"]
        artifact, _, _ = native.observe_sdk(plan=state.plan, producer=state.producer, token=token)
    archive, stream = stack.enter_context(open_reference_archive(
        artifact, token, **products._worker_upload_reference_limits(_BINARY)))
    nested = stack.enter_context(open_stored_reference_archive(archive,
        member["relativePath"], expected_bytes=member["bytes"]))
    try:
        for row in expected["frameworkFiles"]:
            copy_reference_member(nested, "stage/" + row["relativePath"],
                destination / row["relativePath"][len(_PREFIX):], row)
            products.count("swiftSourceFrameworkLogicalBytes", row["bytes"])
    finally:
        if stream is not None:
            products.count("swiftSourceOriginalRangeBytes", stream.transferred)
    def unchanged():
        if native.envelope(record) != envelope:
            raise ValueError("Swift framework authority changed during use")
    stack.callback(unchanged)


def _init_script(private):
    # Fixed task/property binding only. Included build-logic has its own configuration.
    return '''gradle.projectsEvaluated {
    if (gradle.parent != null) return
    def p = gradle.rootProject.project(':codex-agent-runtime-ios')
    def imported = p.tasks.named('importCodexAgentIosSimulatorFramework').get()
    def verify = p.tasks.named('verifyCodexAgentSwiftSimulatorCompilation').get()
    def out = new File(System.getenv('CODEX_AGENT_SWIFT_SOURCE_OUTPUT'))
    imported.importedFrameworkDirectory.set(new File(out, 'imported/CodexAgent.framework'))
    verify.derivedDataDirectory.set(new File(out, 'derived'))
    verify.compiledProductsDirectory.set(new File(out, 'products'))
    verify.reportFile.set(new File(out, 'swift-simulator-compilation.json'))
    verify.outputs.upToDateWhen { false }
    gradle.taskGraph.whenReady { graph ->
        def wanted = [':codex-agent-runtime-ios:verifyAppleToolchain',
            ':codex-agent-runtime-ios:importCodexAgentIosSimulatorFramework',
            ':codex-agent-runtime-ios:verifyCodexAgentSwiftSimulatorCompilation'] as Set
        if ((graph.allTasks.collect { it.path } as Set) != wanted)
            throw new GradleException('Swift retained-input graph changes the fixed consumer-only task set')
    }
}
'''


@products.measured
def run_retained_swift_source(state, *, plan_path, repository_root, environ):
    require_no_signing_secret(environ)
    session = _VERIFICATION_SESSION.get()
    if session is None or type(state) is not products._VerifiedProductState:
        raise ValueError("Swift checks require the existing live verified state")
    root, plan_path = Path(repository_root).resolve(strict=True), Path(plan_path)
    plan_raw = read_regular_file_bytes(plan_path, max_bytes=4 * _LIMIT, reject_symlink_parents=True)
    if (load_json_bytes(plan_raw) != state.plan or products._consumer(state.plan, environ) != state.consumer
            or not any(state.plan["lanes"]["ios-swift-build"][a] for a in ("build", "test"))
            or environ.get("GITHUB_ACTIONS") != "true" or environ.get("GITHUB_JOB") != "retained-swift-source"
            or environ.get("CI_VALIDATION_COMMIT") != state.plan["validationCommit"]
            or environ.get("CI_VALIDATION_TREE") != state.plan["validationTree"]
            or host_classifier() != "macos-arm64" or (environ.get("RUNNER_OS"), environ.get("RUNNER_ARCH")) != ("macOS", "ARM64")):
        raise ValueError("Swift source checks require the current selected Apple Silicon host")
    native = state.completed_frozen
    before = _expected(native, state.consumer, root)
    record = state.prior_by_instance.get(_BINARY)
    if record is None or {k: record[k] for k in _FIELDS} != before["originalInput"]:
        raise ValueError("Swift source state changes its original binary")
    build = require_regular_directory(root / "build", "Swift source build root")
    entry_free = shutil.disk_usage(build).free
    products.count("swiftSourceEntryFreeBytes", entry_free)
    if entry_free < 12 * 1024**3:
        raise ValueError("Swift source check needs 12 GiB free for the unchanged task's private copies/products")
    with tempfile.TemporaryDirectory(prefix="retained-swift-", dir=build) as tmp, ExitStack() as stack:
        private = Path(tmp).resolve(); framework = private / "CodexAgent.framework"
        minimum_free, samples = entry_free, 1
        def sample_free():
            nonlocal minimum_free, samples
            free = shutil.disk_usage(build).free
            minimum_free, samples = min(minimum_free, free), samples + 1
            return free
        def storage_observation():
            try:
                sample_free()
            except OSError:
                products.count("swiftSourceDiskSampleErrors")
            products.count("swiftSourceMinimumObservedFreeBytes", minimum_free)
            products.count("swiftSourceDiskSamples", samples)
        stack.callback(storage_observation)
        from runtime_reference_transport import ENVIRONMENT as authority_environment
        env = {k: v for k, v in environ.items() if k not in {"GITHUB_TOKEN", "GH_TOKEN", "REUSE_AUTHORITY_READ_TOKEN", *authority_environment}}
        env["CODEX_AGENT_SWIFT_SOURCE_OUTPUT"] = str(private / "output")
        wrapper = root / "gradlew"
        if read_regular_file_bytes(wrapper, reject_symlink_parents=True) != git_regular_blob_bytes(
                root, state.producer["commit"], "gradlew", max_bytes=64 * 1024):
            raise ValueError("Swift Gradle wrapper differs from current source")
        from products.gradle_bootstrap import seed_sdk_gradle_dependencies
        seed = private / "build-dependencies"
        require_no_signing_secret(environ)
        products._runtime_worker_checkout(root, state.producer)
        native.check_request(state.rebased_request)
        seed_started = time.perf_counter_ns()
        try:
            seed_sdk_gradle_dependencies(root, state.producer["commit"], wrapper, env, seed)
        except ValueError:
            # The private fixture is retired at exit; retain only its bounded causal tail.
            diagnostic = seed / "gradle.log"
            if diagnostic.is_file() and not diagnostic.is_symlink():
                descriptor, metadata = _open_regular_file(diagnostic, "Swift dependency log", reject_symlink_parents=True)
                with os.fdopen(descriptor, "rb") as stream:
                    stream.seek(max(0, metadata.st_size - 16 * 1024))
                    print(stream.read(16 * 1024).decode("utf-8", errors="replace"), flush=True)
            raise
        finally:
            products.count("swiftSourceDependencySeedElapsedNs", time.perf_counter_ns() - seed_started)
            products._runtime_worker_checkout(root, state.producer)
            native.check_request(state.rebased_request)
            if (_expected(native, state.consumer, root) != before or
                    read_regular_file_bytes(plan_path, reject_symlink_parents=True) != plan_raw):
                raise ValueError("Swift source inputs changed during dependency preparation")
        if sample_free() < 12 * 1024**3:
            raise ValueError("Swift source check needs 12 GiB free after dependency preparation")
        _copy_framework(state, record, before, framework, stack, environ["GITHUB_TOKEN"])
        products.count("swiftSourceAfterFrameworkFreeBytes", sample_free())
        expected_files = [{"relativePath": r["relativePath"][len(_PREFIX):], "bytes": r["bytes"], "sha256": r["sha256"]}
                          for r in before["frameworkFiles"]]
        if memoized_file_inventory(framework) != expected_files:
            raise ValueError("Swift framework differs from the four consumed original leaves")
        init = private / "fixed.init.gradle"; init.write_text(_init_script(private))
        command = [str(wrapper), _TASK, "--offline", "--no-build-cache", "--no-configuration-cache", "--stacktrace",
                   "--init-script", str(init), "-PcodexAgent.iosSimulatorFrameworkDirectory=" + str(framework)]
        log = private / "execution.log"
        def unchanged():
            require_no_signing_secret(environ)
            native.check_request(state.rebased_request)
            products._runtime_worker_checkout(root, state.producer)
            if (_VERIFICATION_SESSION.get() is not session or _expected(native, state.consumer, root) != before
                    or memoized_file_inventory(framework) != expected_files
                    or read_regular_file_bytes(plan_path, reject_symlink_parents=True) != plan_raw
                    or products._consumer(state.plan, environ) != state.consumer):
                raise ValueError("Swift source inputs changed or outlived their owners")
        unchanged(); started = time.perf_counter_ns()
        try:
            with log.open("xb") as output:
                with subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                        stdout=output, stderr=subprocess.STDOUT, start_new_session=True) as child:
                    while child.poll() is None:
                        if sample_free() < 2 * 1024**3 or log.stat().st_size > _LIMIT:
                            os.killpg(child.pid, signal.SIGTERM)
                            try: child.wait(timeout=30)
                            except subprocess.TimeoutExpired:
                                os.killpg(child.pid, signal.SIGKILL); child.wait()
                            raise ValueError("Swift source check crossed its 2 GiB free-space or control-log bound")
                        time.sleep(0.5)
                    if child.returncode:
                        raise subprocess.CalledProcessError(child.returncode, command)
        except (subprocess.CalledProcessError, ValueError, OSError):
            try:
                failure = root / "build/ci/retained-swift-source/failure.log"
                failure.parent.mkdir(parents=True, exist_ok=True)
                descriptor, metadata = _open_regular_file(log, "Swift failure log", reject_symlink_parents=True)
                with os.fdopen(descriptor, "rb") as source:
                    raw = source.read(_LIMIT)
                    if _stat_identity(os.fstat(source.fileno())) != _stat_identity(metadata):
                        raise ValueError("Swift failure log changed during bounded capture")
                with failure.open("xb") as output: output.write(raw)
                if metadata.st_size > _LIMIT:
                    products.count("swiftSourceFailureLogTruncated")
            except (OSError, ValueError) as diagnostic_error:
                products.count("swiftSourceFailureLogCaptureErrors")
                print("Swift failure log could not be retained: " + type(diagnostic_error).__name__, file=sys.stderr)
            raise
        finally:
            products.count("swiftSourceGradleElapsedNs", time.perf_counter_ns() - started)
            unchanged()
        elapsed = time.perf_counter_ns() - started
        report = read_regular_file_bytes(private / "output/swift-simulator-compilation.json", max_bytes=_LIMIT,
                                         reject_symlink_parents=True)
        execution = read_regular_file_bytes(log, max_bytes=_LIMIT, reject_symlink_parents=True)
        record = {"schemaVersion": 1, "kind": "retained-swift-source", "result": "passed", "task": _TASK,
            "producer": state.consumer["producer"], "planSha256": sha256_bytes(plan_raw), **before,
            "executionElapsedNs": elapsed, "reportSha256": sha256_bytes(report), "executionSha256": sha256_bytes(execution)}
        controls = dict(zip(_NAMES, (canonical_json_bytes(record), report, execution)))
        _validate_controls(controls, state.consumer["producer"], sha256_bytes(plan_raw), before)
        unchanged(); stack.close()
        return controls


def _validate_controls(members, producer, plan_sha256, expected):
    if set(members) != set(_NAMES) or sum(map(len, members.values())) > _LIMIT - 4096:
        raise ValueError("Swift source controls change their bounded three-member closure")
    report = load_json_bytes(members[_NAMES[1]])
    if canonical_json_bytes(report) != canonical_json_bytes({"schemaVersion": 1, "result": "passed", "target": "iosSimulatorArm64", **expected["toolchain"]}):
        raise ValueError("Swift compilation report changes the exact current toolchain/result")
    record = load_canonical_json_bytes(members[_NAMES[0]])
    elapsed = require_integer(record.get("executionElapsedNs"), "Swift source execution elapsed", 1)
    exact = {"schemaVersion": 1, "kind": "retained-swift-source", "result": "passed", "task": _TASK,
        "producer": producer, "planSha256": plan_sha256, **expected, "executionElapsedNs": elapsed,
        "reportSha256": sha256_bytes(members[_NAMES[1]]), "executionSha256": sha256_bytes(members[_NAMES[2]])}
    if canonical_json_bytes(record) != canonical_json_bytes(exact) or not members[_NAMES[2]]:
        raise ValueError("Swift controls substitute current source, task or original input")
    return record


def observed_swift_source(native, *, plan, plan_sha256, root, consumer, observation, token):
    producer = consumer["producer"]; before = _expected(native, consumer, root)
    name = f"codex-agent-retained-swift-source-{producer['tree']}-attempt-{producer['runAttempt']}"
    listing = products.paginated_items(f"https://api.github.com/repos/{producer['repository']}/actions/runs/{producer['runId']}/artifacts", "artifacts", token)
    matches = [r for r in listing if r.get("name") == name]
    if len(matches) != 1: raise ValueError("Swift source controls are missing or ambiguous")
    identifier = require_integer(matches[0].get("id"), "Swift source artifact ID", 1)
    digest = require_sha256(matches[0].get("digest"), "Swift source artifact digest")
    artifact = products._contract_ci_upload_metadata(identifier, digest, name, producer, observation["run"], token)
    products._require_artifact_job_window(observation, "product-validation / retained-apple-source / retained-swift-simulator", artifact)
    size = require_integer(artifact["size_in_bytes"], "Swift controls bytes", 1)
    if size > _LIMIT: raise ValueError("Swift source upload exceeds its control-only bound")
    with tempfile.TemporaryDirectory(prefix="swift-source-controls-") as tmp:
        archive = Path(tmp).resolve() / "controls.zip"
        products._reuse_contract_ci_upload(artifact, producer, observation["run"], token,
            destination=archive, limit=_LIMIT, artifact_sha256=digest, size=size)
        inventory, members, transport = verified_zip_contents(archive, max_archive_bytes=_LIMIT,
            max_members=3, max_entry_bytes=_LIMIT, max_total_bytes=_LIMIT, retained_paths=_NAMES,
            max_retained_bytes=_LIMIT, require_sorted=False)
        if transport != {"bytes": size, "sha256": digest} or {r['relativePath'] for r in inventory} != set(_NAMES):
            raise ValueError("Swift upload changes its authenticated closure")
        result = _validate_controls(members, producer, plan_sha256, before)
    if _expected(native, consumer, root) != before:
        raise ValueError("Swift source authority changed during observation")
    return {"ios-swift-build": {"artifactId": identifier, "artifactSha256": digest, "original": result}}


def main(argv=None):
    import argparse
    from reuse_qualification import completed_frozen_options
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "completed-frozen-policy"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    args = parser.parse_args(argv); root = Path(__file__).resolve().parents[3]; args.repository_root = root
    require_no_signing_secret(os.environ)
    plan = products._validate_plan(args.plan, root)
    if not products.validate_remote_build_authorization(plan)[0] or plan['mergeReady'] is not True:
        raise ValueError("Swift source job is not authorized by the current plan")
    destination = root / "build/ci/retained-swift-source/controls"
    if destination.exists() or destination.is_symlink(): raise ValueError("Swift controls must be fresh")
    controls = {}
    def consume(state):
        if controls: raise ValueError("Swift source inputs already consumed")
        controls.update(run_retained_swift_source(state, plan_path=args.plan, repository_root=root, environ=os.environ))
    with tempfile.TemporaryDirectory(prefix="retained-swift-capture-", dir=root / "build") as tmp:
        capture = Path(tmp) / "capture"
        with verification_session(), products._ci_observation_batch(
                (os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]), share_nested=True), completed_frozen_options(args) as completed:
            products.capture_runtime_resume_upload(args.plan, capture, artifact_id=args.artifact_id,
                artifact_sha256=args.artifact_sha256, trusted_workflow_sha=args.trusted_workflow_sha,
                repository_root=root, environ=os.environ, token=os.environ["GITHUB_TOKEN"], state_wave=0,
                allow_earlier_attempt=True, **completed)
            original = capture / "original"; captured_plan = original / "product-resume-inputs/plan/impact-plan.json"
            if read_regular_file_bytes(captured_plan, reject_symlink_parents=True) != read_regular_file_bytes(args.plan, reject_symlink_parents=True):
                raise ValueError("Swift captured plan changes the current plan")
            products.inspect_products(captured_plan, original / "product-resume-state", repository_root=root,
                environ=os.environ, sdk_original_workflow_sha=args.trusted_workflow_sha, _verified_state_consumer=consume, **completed)
        if set(controls) != set(_NAMES): raise ValueError("Swift source check did not produce its exact controls")
        stage = Path(tmp) / "controls"; stage.mkdir()
        for name, raw in controls.items(): (stage / name).write_bytes(raw)
        publish_regular_tree(stage, destination)


if __name__ == "__main__":
    main()
