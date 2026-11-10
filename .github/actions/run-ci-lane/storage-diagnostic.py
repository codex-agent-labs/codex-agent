"""One native-qualified original, two private consumer lifetimes; no producer."""
import argparse
from contextlib import ExitStack, redirect_stderr
import json
import os
from pathlib import Path
import platform
import stat
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "ci"), str(ROOT)]
from products.inventory import (
    _open_regular_file, _stat_identity, canonical_json_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, sha256_bytes,
)
from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId
from products.restore import (
    memoized_file_inventory, object_relative_path, restore_object,
    verification_session, verify_object, write_carrier,
)
from products.sdk_apple_content import _snapshot_apple_tree
from runtime_reference_transport import measured, measured_volume

IDENTITY = dict(product="sdk", component="sdk-ios", phase="metadata", target="ios")
OBJECT = dict(IDENTITY,
    buildKey="sha256:7647170b124a64ea1a161b843e73e7136d2add3a3fef7f68cc438ce7f5d16fcb",
    receiptSha256="sha256:c939473a93d4013d97c312c438117324099fbb03a09d7a117ba0fe07363a6ee5",
    objectSha256="sha256:677e44a4d0e8612c55fd48c375fbbad2fcaa94ec1ecfb588f5a0e75543905ff4")
ORIGINAL = dict(IDENTITY, artifactId=13220870283,
    artifactSha256="sha256:ac1e81a4d6644422e386fcd51fa18cc8e74985e1c5af07239b68b7b532b6a74e",
    jobId=125815314274, workflowSha="48b25312f41467e98fe8faf810102ee9f0b70204")
OBJECT_BYTES = 1365422


def io_observation():
    """Keep Linux storage-byte accounting separate from other Unix block counts."""
    value = {"process": os.getpid(), "storageReadBytes": None, "storageWriteBytes": None,
             "cancelledWriteBytes": None, "descendantStorageBytes": None}
    if sys.platform == "linux":
        try:
            rows = dict(line.split(": ", 1) for line in Path("/proc/self/io").read_text().splitlines())
            value.update(storageReadBytes=int(rows["read_bytes"]),
                         storageWriteBytes=int(rows["write_bytes"]),
                         cancelledWriteBytes=int(rows["cancelled_write_bytes"]))
        except (OSError, ValueError, KeyError):
            pass
    if sys.platform != "win32":
        import resource
        for label, who in (("self", resource.RUSAGE_SELF), ("waitedChildren", resource.RUSAGE_CHILDREN)):
            r = resource.getrusage(who)
            value[label + "BlockOperations"] = {"input": r.ru_inblock, "output": r.ru_oublock}
    return value


def free_bytes(path):
    import shutil
    return shutil.disk_usage(path).free


def current_consumer(root, environ):
    import product_reuse as products
    from products.receipt import validate_producer
    event = json.loads(read_regular_file_bytes(Path(environ["GITHUB_EVENT_PATH"]), max_bytes=1024**2,
                                               reject_symlink_parents=True))
    revision = products._git_value(root, "rev-parse", "HEAD")
    workflow = ".github/workflows/portable-reuse-proof.yml"
    if (environ.get("GITHUB_ACTIONS") != "true" or environ.get("GITHUB_EVENT_NAME") != "pull_request"
            or environ.get("GITHUB_REPOSITORY") != "codex-agent-labs/codex-agent"
            or event.get("action") != "labeled" or event.get("number") != 31
            or event.get("label", {}).get("name") not in ("ci:storage-consumer-diagnostics",
                                                        "ci:storage-consumer-macos-x64")
            or event["pull_request"]["head"]["repo"]["full_name"] != environ["GITHUB_REPOSITORY"]
            or event["pull_request"]["head"]["repo"]["fork"]
            or event["pull_request"]["head"]["sha"] != revision
            or environ.get("EXPECTED_SOURCE") != revision
            or not environ.get("GITHUB_WORKFLOW_REF", "").startswith(
                environ["GITHUB_REPOSITORY"] + "/" + workflow + "@")):
        raise ValueError("Storage diagnostic requires its exact hosted PR/source election")
    producer = validate_producer(dict(repository=environ["GITHUB_REPOSITORY"], workflowPath=workflow,
        commit=revision, tree=products._git_value(root, "rev-parse", "HEAD^{tree}"),
        event="pull_request", pullRequest=31, runId=int(environ["GITHUB_RUN_ID"]),
        runAttempt=int(environ["GITHUB_RUN_ATTEMPT"])))
    products._runtime_worker_checkout(root, producer)
    return {"kind": "ci", "producer": producer}


def selected_original(capability):
    from completed_sdk_reuse import original_worker_member
    if set(capability.completed_phases()) != set(PHASE_INSTANCE_IDS):
        raise ValueError("Diagnostic requires current full native112 authority")
    extension = capability.sdk_extension()
    if extension is None or not original_worker_member(extension["spec"]):
        raise ValueError("Diagnostic requires the exact scoped original-worker reader")
    rows = [r for r in extension["spec"]["completedPhases"]
            if all(r.get(k) == v for k, v in IDENTITY.items())]
    originals = [r for r in extension["spec"]["originals"]
                 if all(r.get(k) == v for k, v in IDENTITY.items())]
    members = [r for r in extension["proof"]["members"] if r["sha256"] == OBJECT["objectSha256"]]
    if (len(rows) != 1 or any(rows[0].get(k) != v for k, v in OBJECT.items())
            or originals != [ORIGINAL] or len(members) != 1 or members[0]["bytes"] != OBJECT_BYTES):
        raise ValueError("Diagnostic cannot select another object or a bulk carrier")
    envelope = capability.envelope(OBJECT)
    if envelope is None:
        raise ValueError("Diagnostic receipt lacks native authority")
    return envelope


@measured
def consume(label, archive, envelope, consumer, parent):
    """Exercise production restore, reference forwarding and independent staging."""
    receipt = envelope["receipt"]
    instance = PhaseInstanceId(*(receipt[k] for k in ("product", "component", "phase", "target")))
    record = {**{k: getattr(instance, k) for k in ("product", "component", "phase", "target")},
              "buildKey": receipt["buildKey"], "receiptSha256": envelope["receiptSha256"],
              "objectSha256": envelope["objectSha256"]}
    arguments = dict(build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                     object_sha256=record["objectSha256"])
    before_io, before_free, start = io_observation(), free_bytes(parent), time.perf_counter_ns()
    with tempfile.TemporaryDirectory(prefix=label + "-", dir=parent) as directory:
        private = Path(directory).resolve()
        restored = restore_object(archive, private / "restored", **arguments)
        free_after_restore = free_bytes(parent)
        if restored["receiptBytes"] != envelope["receiptBytes"]:
            raise ValueError("Restoration changed the original receipt")
        expected = memoized_file_inventory(private / "restored")
        phase = dict(record, state="reused", source="local", misses=[],
                     transportSource={"kind": "local", "cacheRelativePath":
                                      object_relative_path(record["buildKey"], record["receiptSha256"])})
        resolution = dict(schemaVersion=1, result="complete", fullReuse=True, phases=[phase],
                          matrices={"contract": [], "runtime": [], "sdk": []})
        forwarded = write_carrier(private / "forwarded", resolution, (instance,), {instance: archive},
                                  consumer, object_root=archive.parent)
        free_after_reference = free_bytes(parent)
        if forwarded["objects"][0]["receiptBytes"] != envelope["receiptBytes"]:
            raise ValueError("Reference forwarding changed the original receipt")
        controls = memoized_file_inventory(private / "forwarded")
        if any(row["relativePath"].endswith(".zip") for row in controls):
            raise ValueError("Reference forwarding unexpectedly copied the object")
        _snapshot_apple_tree(private / "restored", private / "staged")
        free_after_staging = free_bytes(parent)
        if (memoized_file_inventory(private / "staged") != expected
                or memoized_file_inventory(private / "restored") != expected):
            raise ValueError("Independent staging changed content")
        for row in expected:
            a, b = ((private / name / row["relativePath"]).stat()
                    for name in ("restored", "staged"))
            if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino) or a.st_nlink != 1 or b.st_nlink != 1:
                raise ValueError("Independent staging contains a writable alias")
            if stat.S_IMODE(a.st_mode) != stat.S_IMODE(b.st_mode):
                raise ValueError("Independent staging changed file mode")
        verified = verify_object(archive, **arguments)
        if verified["receiptBytes"] != envelope["receiptBytes"]:
            raise ValueError("Original object changed during consumption")
        result = dict(label=label, receiptSha256=envelope["receiptSha256"],
            stagedInventorySha256=sha256_bytes(canonical_json_bytes(expected)),
            stageFiles=len(expected), stageLogicalBytes=sum(r["bytes"] for r in expected),
            forwardedControlBytes=sum(r["bytes"] for r in controls), forwardedObjectBytes=0,
            independentInodes=True, freeBytesBefore=before_free, ioBefore=before_io,
            freeBytesAfterRestore=free_after_restore, freeBytesAfterReference=free_after_reference,
            freeBytesAfterStaging=free_after_staging)
    if private.exists():
        raise ValueError("Private consumer scratch survived owner exit")
    result.update(elapsedNs=time.perf_counter_ns()-start, freeBytesAfterCleanup=free_bytes(parent),
                  ioAfterCleanup=io_observation(), absentAfterExit=True)
    return result


def run(root, policy_path, output, environ):
    import product_reuse as products
    import reuse_qualification as native
    from products.signing_isolation import require_no_signing_secret
    require_no_signing_secret(environ)
    consumer = current_consumer(root, environ)
    raw = read_regular_file_bytes(policy_path, max_bytes=4096, reject_symlink_parents=True)
    policy = load_canonical_json_bytes(raw)
    native.validate_completed_reuse_policy(policy)
    revision = consumer["producer"]["commit"]
    if policy["consumerCommit"] != revision or "sdkCompletion" not in policy:
        raise ValueError("Diagnostic requires an independently provisioned current SDK policy")
    owners = ExitStack()
    result = dict(schemaVersion=1, diagnosticOnly=True, passed=False, consumer=consumer,
        policySha256=sha256_bytes(raw), original=ORIGINAL, object=OBJECT, passes=[],
        platform=platform.platform(), machine=platform.machine(),
        observedDevice=output.parent.stat().st_dev, filesystemType=None,
        freeBytesBefore=free_bytes(output.parent), ioBefore=io_observation(),
        measurementLimits=[
            "First/repeat share one authenticated original and one private verification session; not two cold workers.",
            "measured_volume scopes cover acquisition, each consumer through cleanup and final owner/cache exit; free space is shared-volume sampled capacity, not exclusive allocation. Synchronous restore/reference/staging observations include live scratch but do not establish a continuous peak.",
            "Linux /proc/self/io reports kernel task I/O accounting, subject to delayed/cancelled writes; not an independently complete descendant or device-wide physical I/O census.",
            "Unix ru_inblock/ru_oublock are operation counts, never byte estimates. Unsupported byte counters remain null.",
            "Independent inode identity and logical clone bytes do not establish unique shared extents. No global sync or physical-savings inference.",
            "This diagnostic performs no explicit producer, Gradle, qualification issuance or new receipt operation; it is not a recursive process census."])
    started = time.perf_counter_ns()
    try:
        with measured_volume("storage_diagnostic_acquisition", output.parent):
            directory = owners.enter_context(tempfile.TemporaryDirectory(prefix="held-storage-"))
            private = Path(directory).resolve()
            if private.stat().st_dev != output.parent.stat().st_dev:
                raise ValueError("Diagnostic scratch and volume observation must share a device")
            session = owners.enter_context(verification_session())
            if session["root"].stat().st_dev != output.parent.stat().st_dev:
                raise ValueError("Verification cache must share the measured device")
            owners.enter_context(products._ci_observation_batch())
            cap, report = native.fetch_completed_frozen(private / "native",
                consumer_commit=revision, verifier_policy_sha256=policy["verifierPolicySha256"],
                repository_root=root, revision=revision, token=environ["GITHUB_TOKEN"],
                sdk_completion=policy["sdkCompletion"],
                **({"requalification_baseline": policy["requalificationBaseline"]}
                   if "requalificationBaseline" in policy else {}),
                **native._native_pin_arguments({k: policy[k] for k in (
                    "artifactId", "artifactSha256", "runId", "runAttempt", "signerCommit", "sourceCommit")}))
            envelope = selected_original(cap)
            archive = private / "object.zip"
            # This fixed SDK extension branch observes source/original jobs and
            # their native locators; it does not use an impact plan or impersonate ci.yml.
            cap.capture_object(OBJECT, archive, plan=None, producer=consumer["producer"],
                               trusted_workflow_sha=ORIGINAL["workflowSha"], token=environ["GITHUB_TOKEN"])
            descriptor, initial = _open_regular_file(archive, "Diagnostic original", reject_symlink_parents=True)
            owners.callback(os.close, descriptor)
            if initial.st_size != OBJECT_BYTES:
                raise ValueError("Diagnostic original size changed")
            result["nativeAuthentication"] = report
        for label in ("first", "repeat"):
            with measured_volume("storage_diagnostic_" + label + "_through_cleanup", output.parent):
                result["passes"].append(consume(label, archive, envelope, consumer, private))
                if (_stat_identity(os.fstat(descriptor)) != _stat_identity(initial)
                        or _stat_identity(archive.stat()) != _stat_identity(initial)):
                    raise ValueError("Held original changed during diagnostic")
        if result["passes"][0]["stagedInventorySha256"] != result["passes"][1]["stagedInventorySha256"]:
            raise ValueError("Matched consumer inventories differ")
        result["verificationSession"] = {k: session[k] for k in ("hits", "misses", "bytes", "uploadBytes")}
    finally:
        with measured_volume("storage_diagnostic_final_owner_exit", output.parent):
            owners.close()
    if private.exists():
        raise ValueError("Private acquisition/cache owner survived exit")
    if (read_regular_file_bytes(policy_path, max_bytes=4096, reject_symlink_parents=True) != raw
            or products._git_value(root, "rev-parse", "HEAD") != revision):
        raise ValueError("Diagnostic authority or source changed during use")
    products._runtime_worker_checkout(root, consumer["producer"])
    result.update(passed=True, elapsedNs=time.perf_counter_ns()-started,
                  ownersExited=True, freeBytesAfterOwners=free_bytes(output.parent),
                  ioAfterOwners=io_observation(), exclusivePhysicalAllocatedBytes=None)
    return result


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--completed-frozen-policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.parent.resolve(strict=True) != output.parent:
        raise ValueError("Diagnostic output parent must be normalized")
    output.mkdir(mode=0o700, exist_ok=False)
    result = None
    with (output / "trace.log").open("x") as trace, redirect_stderr(trace):
        try:
            result = run(ROOT, args.completed_frozen_policy, output, os.environ)
        except Exception as error:
            (output / "failure.json").write_bytes(canonical_json_bytes({
                "schemaVersion": 1, "diagnosticOnly": True, "passed": False,
                "errorType": type(error).__name__, "error": str(error)}))
            raise
    (output / "result.json").write_bytes(canonical_json_bytes(result))


if __name__ == "__main__":
    main()

