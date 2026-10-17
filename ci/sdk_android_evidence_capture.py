"""Build and retain Android test-consumer transports, without device admission.

This retains official transport plus the complete lane bytes and reuses the
existing lane/plan checker. APK compilation consumes authenticated B/P artifacts;
its build-only receipt never claims legacy unit tests or lint. A later consumer
must authenticate the independently approved attach tooling and run the complete
Firebase APK/AAR/XML gate. No transport or structural check grants that authority.
"""

import argparse
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Mapping

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
import sdk_android_upload_locator as upload_locator
from products.inventory import (
    canonical_json_bytes, load_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_integer,
    require_sha256, sha256_bytes, sha256_file, verified_zip_contents,
    write_canonical_json,
)
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from products.restore import regular_file_inventory, verification_scoped
from products.sdk_android_observation import SUBMISSION_FILES
from products.sdk_compatibility import load_sdk_compatibility_request
from products.sdk_maven import MAVEN_GROUPS
from impact import validate_remote_build_authorization
from receipt import INPUT_NAMES, create_receipt, validate_receipt, write_json
from reuse import download_artifact


_FIREBASE_PREFIX = "payload/external/android-runtime-evidence/"
_FIREBASE_FILES = {
    _FIREBASE_PREFIX + name for name in (
        "android-runtime-evidence.json",
        "firebase-test-matrix.json",
        "RuntimeBootstrapDeviceTest.xml",
        "android-runtime-evidence-debug.apk",
        "android-runtime-evidence-debug-androidTest.apk",
        "codex-agent-runtime-android-release.aar",
        "firebase-android-runtime-verification.json",
    )
}


def _check_lane(plan: Path, lane: Path, value: dict) -> bytes:
    """Run the existing trusted structural checker, then bind the final closure."""
    receipt_bytes = read_regular_file_bytes(
        lane / "lane-receipt.json", max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt = load_json_bytes(receipt_bytes)
    if receipt.get("toolchain", {}).get("evidenceScope") == SCOPE:
        # This selects a stricter build-only transport, not a device verdict or
        # legacy test/lint success. Full signed-tooling admission is unchanged.
        check(plan, lane, final=True)
        return receipt_bytes
    tree = value["validationTree"]
    command = [
        sys.executable, str(Path(__file__).resolve().with_name("evidence.py")), "check",
        "--artifact", str(lane), "--plan", str(plan),
        "--expected-commit", value["validationCommit"],
        "--expected-artifact", f"codex-agent-ci-android-{tree}",
        "--expected-plan-artifact", f"codex-agent-ci-plan-{tree}",
        "--expected-repository", value["repository"], "--expected-event", value["event"],
    ]
    failure = None
    with tempfile.TemporaryDirectory(prefix="android-evidence-check-") as temporary:
        bytecode = Path(temporary).resolve() / "python-bytecode"
        environment = {
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1",
            "PYTHONPYCACHEPREFIX": str(bytecode),
            "PYTHONPATH": str(Path(__file__).resolve().parent),
        }
        try:
            subprocess.run(command, check=True, env=environment, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError) as error:
            failure = error
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("Android evidence check created its isolated bytecode namespace")
    if failure is not None:
        raise ValueError("Android original lane or impact plan failed its existing evidence check") from failure
    if read_regular_file_bytes(lane / "lane-receipt.json", reject_symlink_parents=True) != receipt_bytes:
        raise ValueError("Android lane receipt changed during structural validation")
    firebase = {
        record.get("relativePath") for record in receipt.get("evidence", ())
        if type(record) is dict and record.get("kind") == "firebase-runtime-evidence"
    }
    if firebase != _FIREBASE_FILES:
        raise ValueError("Android upload lacks the exact final seven-file Firebase closure")
    return receipt_bytes


def capture_android_evidence(
    plan_path: Path,
    candidate_root: Path,
    destination: Path,
    *,
    trusted_workflow_sha: str,
    trusted_android_workflow_sha: str,
    environ: Mapping[str, str] | None = None,
    token: str,
    expected_revision: str | None = None,
) -> dict:
    """Retain one fixed final upload; return transport metadata, not admission."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if type(token) is not str or not token:
        raise ValueError("Android evidence capture requires an observation token")
    root = Path(candidate_root).resolve(strict=True)
    source = Path(plan_path).absolute()
    destination = Path(destination).absolute()

    def output_safe():
        _require_capability_output_separate(destination, (root, source))
        if destination.exists() or destination.is_symlink():
            raise ValueError("Android evidence capture destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(
        source, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    inventory_sources = {
        name: source.parent / "inventories/android" / name for name in INPUT_NAMES.values()
    }
    inventory_bytes = {
        name: read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                      reject_symlink_parents=True)
        for name, path in inventory_sources.items()
    }
    with tempfile.TemporaryDirectory(prefix="android-evidence-capture-") as temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "input-plan/impact-plan.json"
        captured_plan.parent.mkdir()
        captured_plan.write_bytes(plan_bytes)
        captured_inventories = captured_plan.parent / "inventories/android"
        captured_inventories.mkdir(parents=True)
        for name, contents in inventory_bytes.items():
            (captured_inventories / name).write_bytes(contents)
        plan = products._validate_plan(captured_plan, root, expected_revision=expected_revision)
        plan_value = canonical_json_bytes(plan)
        producer = products.validate_producer(products._consumer(plan, environment)["producer"])
        locator = upload_locator.locate_android_validation_upload(
            source, root, trusted_workflow_sha=trusted_workflow_sha,
            trusted_android_workflow_sha=trusted_android_workflow_sha,
            environ=environment, token=token,
            expected_revision=expected_revision,
        )
        artifact_id = require_integer(locator.get("artifact_id"), "Android artifact ID", 1)
        artifact_sha256 = require_sha256(locator.get("artifact_sha256"), "Android artifact digest")

        def unchanged():
            require_no_signing_secret(environment)
            if (read_regular_file_bytes(source, max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != plan_bytes
                    or read_regular_file_bytes(captured_plan) != plan_bytes
                    or any(read_regular_file_bytes(inventory_sources[name], max_bytes=16 * 1024 * 1024,
                                                   reject_symlink_parents=True) != contents
                           or read_regular_file_bytes(captured_inventories / name) != contents
                           for name, contents in inventory_bytes.items())
                    or canonical_json_bytes(plan) != plan_value
                    or canonical_json_bytes(products._validate_plan(captured_plan, root, expected_revision=expected_revision)) != plan_value
                    or products.validate_producer(products._consumer(plan, environment)["producer"]) != producer):
                raise ValueError("Android capture plan or current producer changed")

        # Do not begin the download after a locator was derived from changed input.
        unchanged()
        api = f"https://api.github.com/repos/{upload_locator.REPOSITORY}/actions"
        url = f"{api}/artifacts/{artifact_id}"
        artifact = products.api_json(url, token)
        expected_name = f"codex-agent-ci-android-{producer['tree']}"
        workflow_run = artifact.get("workflow_run") if type(artifact) is dict else None
        if (type(artifact) is not dict
                or require_integer(artifact.get("id"), "Android artifact ID", 1) != artifact_id
                or artifact.get("name") != expected_name or artifact.get("expired") is not False
                or artifact.get("digest") != artifact_sha256
                or artifact.get("archive_download_url") != url + "/zip"
                or type(workflow_run) is not dict
                or require_integer(workflow_run.get("id"), "Android artifact run", 1) != producer["runId"]):
            raise ValueError("Android artifact changed after its fixed locator was observed")
        artifact_bytes = canonical_json_bytes(artifact)
        unchanged()
        archive_bytes = download_artifact(artifact, token)

        prepared = private / "captured"
        prepared.mkdir()
        retained_plan = prepared / "plan/impact-plan.json"
        retained_plan.parent.mkdir()
        retained_plan.write_bytes(plan_bytes)
        retained_inventories = retained_plan.parent / "inventories/android"
        retained_inventories.mkdir(parents=True)
        for name, contents in inventory_bytes.items():
            (retained_inventories / name).write_bytes(contents)
        archive = prepared / "original-upload.zip"
        archive.write_bytes(archive_bytes)
        zipped, _, _ = verified_zip_contents(
            archive, retained_paths=(), allow_empty_members=True,
            **products._CATALOG_ZIP_LIMITS,
        )
        original = prepared / "original"
        products.safe_extract(archive, original)
        if regular_file_inventory(original, allow_empty=True) != zipped:
            raise ValueError("Android extraction differs from the exact original upload")
        receipt_bytes = _check_lane(retained_plan, original, plan)
        transport = {
            "schemaVersion": 1,
            "kind": "android-evidence-transport",
            "artifact": artifact,
            "locator": locator,
            "captureProducer": producer,
            "laneReceiptSha256": sha256_bytes(receipt_bytes),
        }
        write_canonical_json(prepared / "capture-transport.json", transport)
        original_inventory = regular_file_inventory(original, allow_empty=True)
        transport_bytes = canonical_json_bytes(transport)
        retained = {
            "original-upload.zip": archive_bytes,
            "plan/impact-plan.json": plan_bytes,
            "capture-transport.json": transport_bytes,
            **{f"plan/inventories/android/{name}": contents
               for name, contents in inventory_bytes.items()},
        }
        expected_inventory = sorted((
            [{**record, "relativePath": "original/" + record["relativePath"]}
             for record in zipped] +
            [{"relativePath": name, "bytes": len(contents),
              "sha256": sha256_bytes(contents)} for name, contents in retained.items()]
        ), key=lambda record: record["relativePath"])
        unchanged()
        if (sha256_file(archive) != artifact_sha256
                or regular_file_inventory(original, allow_empty=True) != original_inventory
                or original_inventory != zipped
                or read_regular_file_bytes(retained_plan) != plan_bytes
                or any(read_regular_file_bytes(retained_inventories / name) != contents
                       for name, contents in inventory_bytes.items())
                or read_regular_file_bytes(original / "lane-receipt.json",
                                           max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != receipt_bytes
                or canonical_json_bytes(artifact) != artifact_bytes
                or read_regular_file_bytes(prepared / "capture-transport.json") != transport_bytes):
            raise ValueError("Android original upload or retained capture changed before publication")
        if regular_file_inventory(prepared, allow_empty=True) != expected_inventory:
            raise ValueError("Android prepared capture differs from its original inputs")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True,
                             expected_inventory=expected_inventory)
    require_no_signing_secret(environment)
    return transport


SCOPE = "sdk-android-apk-consumer-v1"
TASKS = (":tooling:android-runtime-evidence:assembleDebug",
         ":tooling:android-runtime-evidence:assembleDebugAndroidTest")
POLICY_PROPERTIES = {
    "packageStage": "androidEvidencePackageStage",
    "packageReceipt": "androidEvidencePackageReceipt",
    "binaryStage": "androidEvidenceBinaryStage",
    "binaryReceipt": "androidEvidenceBinaryReceipt",
    "compatibilityRequest": "androidEvidenceCompatibilityRequest",
    "binaryContractEvidence": "androidEvidenceBinaryContractEvidence",
}
CONTROL_FILES = {"apk-execution.json", "apk-build.log", "binary-receipt.json", "package-receipt.json"}


def _authorized_plan(plan):
    value = load_json_bytes(read_regular_file_bytes(plan, reject_symlink_parents=True))
    authorized, reason = validate_remote_build_authorization(value)
    if (not authorized or reason != {"pull_request": "pull-request-final",
            "merge_group": "merge-group", "workflow_dispatch": "protected-dispatch"}.get(value.get("event"))
            or value.get("schemaVersion") != 1 or value.get("mergeReady") is not True
            or value.get("androidEvidenceRequired") is not True):
        raise ValueError("APK consumer requires authorized Android evidence work")
    return value


@verification_scoped
def check(plan, lane, *, final=False):
    """Authenticate transport structure and build coverage, not device success."""
    plan, lane = Path(plan), Path(lane)
    value = _authorized_plan(plan)
    receipt = validate_receipt(lane / "lane-receipt.json", plan, lane, "android",
                               categories=("production",))
    if (receipt["artifactName"] != "codex-agent-ci-android-" + value["validationTree"]
            or receipt["toolchain"].get("evidenceScope") != SCOPE
            or receipt["toolchain"]["validationActions"] != "build"):
        raise ValueError("APK consumer must explicitly claim build only, never legacy test/lint success")
    # Check every inventory, without inventing test/metadata action coverage.
    for name in INPUT_NAMES.values():
        if read_regular_file_bytes(lane / name, reject_symlink_parents=True) != read_regular_file_bytes(
                plan.parent / "inventories/android" / name, reject_symlink_parents=True):
            raise ValueError("APK consumer inventory differs from the original plan")
    originals = set(SUBMISSION_FILES.values()) - {"lane-receipt.json"}
    artifacts = {row["relativePath"] for row in receipt["artifacts"]}
    evidence = {row["relativePath"] for row in receipt["evidence"]}
    if (artifacts != CONTROL_FILES | (set() if final else originals)
            or evidence != (_FIREBASE_FILES if final else set())
            or any(row["kind"] != "firebase-runtime-evidence" for row in receipt["evidence"])):
        raise ValueError("APK consumer transport has an unexpected exact inventory")
    execution = load_json_bytes(read_regular_file_bytes(lane / "apk-execution.json", reject_symlink_parents=True))
    if (execution.get("kind") != SCOPE or execution.get("tasks") != list(TASKS)
            or type(execution.get("exitCode")) is not int or execution["exitCode"] != 0
            or execution.get("candidateCommit") != value["validationCommit"]
            or execution.get("candidateTree") != value["validationTree"]):
        raise ValueError("APK consumer execution differs from the candidate and allowed tasks")
    for phase in ("binary", "package"):
        raw = read_regular_file_bytes(lane / (phase + "-receipt.json"), reject_symlink_parents=True)
        if execution.get(phase + "ReceiptSha256") != sha256_bytes(raw):
            raise ValueError("APK consumer changes its selected original receipt")
    return receipt


def command(root, policy):
    """Only explicit artifact properties; no product build or source fallback."""
    if set(policy) != set(POLICY_PROPERTIES):
        raise ValueError("APK consumer needs the exact six authenticated import inputs")
    paths = {key: Path(value) for key, value in policy.items()}
    if any(not p.is_absolute() or p.resolve(strict=True) != p for p in paths.values()):
        raise ValueError("APK consumer inputs must be normalized absolute regular paths")
    request = load_sdk_compatibility_request(paths["compatibilityRequest"])
    properties = {"codexAgent." + POLICY_PROPERTIES[key]: str(value) for key, value in paths.items()}
    for field, name in (("contract_payload", "contractPayload"),
                        ("contract_metadata_receipt", "contractMetadataReceipt"),
                        ("contract_attestation", "contractAttestation"),
                        ("contract_attestation_signature", "contractAttestationSignature"),
                        ("contract_public_key", "contractPublicKey")):
        properties["codexAgent." + name] = str(request[field])
    properties["codexAgent.contractVersion"] = (root / "gradle/release/versions/contract.txt").read_text().strip()
    return [str(root / "gradlew"), *TASKS, *["-P" + key + "=" + value for key, value in properties.items()],
            "--configuration-cache", "--configuration-cache-problems=fail", "--stacktrace", "--console=plain"]


@verification_scoped
def produce(root, plan, policy, destination):
    require_no_signing_secret(os.environ)
    root = Path(root).resolve(strict=True)
    plan, destination = Path(plan).absolute(), Path(destination).absolute()
    _require_capability_output_separate(destination, (plan, *map(Path, policy.values())))
    if destination.exists() or destination.is_symlink():
        raise ValueError("APK consumer destination must be fresh")
    value = products._validate_plan(plan, root)
    _authorized_plan(plan)
    producer = products.validate_producer(products._consumer(value, os.environ)["producer"])
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip() != producer["commit"]:
        raise ValueError("APK consumer checkout differs from its planned producer")
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=root, check=True)
    argv = command(root, policy)
    diagnostics = destination.with_name(destination.name + "-diagnostics")
    _require_capability_output_separate(diagnostics, (plan, destination, *map(Path, policy.values())))
    diagnostics.mkdir(parents=True, exist_ok=False)
    paths = [plan, *map(Path, policy.values())]
    before = {p: regular_file_inventory(p) if p.is_dir() else read_regular_file_bytes(p, reject_symlink_parents=True)
              for p in paths}

    def unchanged():
        require_no_signing_secret(os.environ)
        if any((regular_file_inventory(p) if p.is_dir() else read_regular_file_bytes(p, reject_symlink_parents=True))
               != expected for p, expected in before.items()):
            raise ValueError("APK consumer original input changed")
        subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=root, check=True)

    with tempfile.TemporaryDirectory(prefix="android-apk-", dir=diagnostics.parent) as temporary:
        prepared = Path(temporary).resolve()
        started = time.monotonic()
        with (diagnostics / "apk-build.log").open("xb") as log:
            result = subprocess.run(argv, cwd=root, stdout=log, stderr=subprocess.STDOUT)
        receipts = {phase: before[Path(policy[phase + "Receipt"])] for phase in ("binary", "package")}
        write_canonical_json(diagnostics / "apk-execution.json", {
            "kind": SCOPE, "tasks": list(TASKS), "command": argv, "exitCode": result.returncode,
            "candidateCommit": producer["commit"], "candidateTree": producer["tree"],
            "seconds": str(time.monotonic() - started),
            **{phase + "ReceiptSha256": sha256_bytes(raw) for phase, raw in receipts.items()},
        })
        unchanged()
        result.check_returncode()
        version = load_json_bytes(receipts["binary"])["productVersion"]
        aar = (Path(policy["binaryStage"]) / "outputs/maven" / Path(*MAVEN_GROUPS["sdk-android"].split(".")) /
               "codex-agent-runtime-android" / version / f"codex-agent-runtime-android-{version}.aar")
        for name, relative in SUBMISSION_FILES.items():
            if name == "lane-receipt.json":
                continue
            source = aar if name == "runtime.aar" else root / relative.removeprefix("payload/")
            raw = read_regular_file_bytes(source, max_bytes=512 * 1024 * 1024, reject_symlink_parents=True)
            if not raw:
                raise ValueError("APK consumer output is empty")
            target = prepared / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        for phase, raw in receipts.items():
            (prepared / (phase + "-receipt.json")).write_bytes(raw)
        for name in ("apk-execution.json", "apk-build.log"):
            (prepared / name).write_bytes(read_regular_file_bytes(diagnostics / name, reject_symlink_parents=True))
        java = subprocess.check_output([str(Path(os.environ["JAVA_HOME"]) / "bin/java"), "-version"],
                                       stderr=subprocess.STDOUT, text=True).strip()
        artifact_paths = CONTROL_FILES | (set(SUBMISSION_FILES.values()) - {"lane-receipt.json"})
        create_receipt(argparse.Namespace(plan=plan, lane="android", output=prepared,
            workflow_path=producer["workflowPath"], artifact_name="codex-agent-ci-android-" + producer["tree"],
            run_id=producer["runId"], run_attempt=producer["runAttempt"],
            runner=["os=" + os.environ["RUNNER_OS"], "arch=" + os.environ["RUNNER_ARCH"]],
            toolchain=["java=" + java, "evidenceScope=" + SCOPE, "validationActions=build"],
            artifact=[path + "=apk-consumer-input" for path in sorted(artifact_paths)], evidence=[]))
        check(plan, prepared)
        unchanged()
        publish_regular_tree(prepared, destination, allow_empty=True)
    unchanged()


@verification_scoped
def attach(plan, lane, source, destination):
    """Create a new final transport; preserve the original APK upload/receipt."""
    plan, lane, source, destination = map(Path, (plan, lane, source, destination))
    _require_capability_output_separate(destination, (plan, lane, source))
    if destination.exists() or destination.is_symlink():
        raise ValueError("Final APK evidence destination must be fresh")
    receipt = check(plan, lane)
    before = {p: regular_file_inventory(p, allow_empty=True) for p in (lane, source)}
    plan_before = read_regular_file_bytes(plan, reject_symlink_parents=True)
    if {row["relativePath"] for row in before[source]} != {p.removeprefix(_FIREBASE_PREFIX) for p in _FIREBASE_FILES}:
        raise ValueError("Final APK evidence requires the exact seven-file Firebase closure")
    for name, relative in SUBMISSION_FILES.items():
        if name == "lane-receipt.json":
            continue
        if read_regular_file_bytes(lane / relative, reject_symlink_parents=True) != read_regular_file_bytes(
                source / Path(relative).name, reject_symlink_parents=True):
            raise ValueError("Firebase final evidence substituted submitted APK/AAR bytes")
    with tempfile.TemporaryDirectory(prefix="android-final-") as temporary:
        prepared = Path(temporary).resolve()
        final = deepcopy(receipt)
        final["artifacts"] = [row for row in receipt["artifacts"] if row["relativePath"] in CONTROL_FILES]
        for path in CONTROL_FILES | set(INPUT_NAMES.values()):
            (prepared / path).write_bytes(read_regular_file_bytes(lane / path, reject_symlink_parents=True))
        final["evidence"] = []
        for relative in sorted(_FIREBASE_FILES):
            target = prepared / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = read_regular_file_bytes(source / Path(relative).name, reject_symlink_parents=True)
            target.write_bytes(raw)
            final["evidence"].append({"relativePath": relative, "kind": "firebase-runtime-evidence",
                                      "sha256": sha256_bytes(raw).removeprefix("sha256:")})
        write_json(prepared / "lane-receipt.json", final)
        check(plan, prepared, final=True)
        if any(regular_file_inventory(p, allow_empty=True) != v for p, v in before.items()) or read_regular_file_bytes(plan) != plan_before:
            raise ValueError("APK/Firebase originals changed during final attachment")
        publish_regular_tree(prepared, destination, allow_empty=True)
    if any(regular_file_inventory(p, allow_empty=True) != v for p, v in before.items()) or read_regular_file_bytes(plan) != plan_before:
        raise ValueError("APK/Firebase originals changed during publication")


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("mode", choices=("produce", "check", "attach"))
    parser.add_argument("--plan", type=Path, required=True)
    for name in ("lane", "source", "destination", "repository", "policy"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    if args.mode == "produce":
        produce(args.repository, args.plan, load_json_bytes(read_regular_file_bytes(args.policy)), args.destination)
    elif args.mode == "attach":
        attach(args.plan, args.lane, args.source, args.destination)
    else:
        check(args.plan, args.lane, final=args.final)


if __name__ == "__main__":
    main()
