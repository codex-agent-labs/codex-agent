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
    canonical_json_bytes, load_json_bytes, load_canonical_json_bytes, publish_regular_tree,
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
# The evidence-only settings filter admits the KMP root but not its Android
# available-at target. Extend that same authenticated repository for these two
# consumers, without changing product settings/keys or permitting any fallback.
CONTRACT_ANDROID_INIT = """gradle.settingsEvaluated { settings ->
    if (settings.rootProject.name != 'codex-agent') return
    def tasks = gradle.startParameter.taskNames
    if (tasks != [':tooling:android-runtime-evidence:assembleDebug',
                  ':tooling:android-runtime-evidence:assembleDebugAndroidTest'] ||
        !gradle.startParameter.projectProperties['codexAgent.androidEvidencePackageStage']) {
        throw new GradleException('Contract Android filter is reserved for artifact-only APK consumers')
    }
    def repositories = settings.dependencyResolutionManagement.repositories
    def authenticated = repositories.getByName('AUTHENTICATED_SDK_CONTRACT_BUNDLE')
    repositories.exclusiveContent {
        forRepositories(authenticated)
        filter { includeModule('io.github.codex-agent-labs', 'codex-agent-core-android') }
    }
}
"""
POLICY_PROPERTIES = {
    "packageStage": "androidEvidencePackageStage",
    "packageReceipt": "androidEvidencePackageReceipt",
    "binaryStage": "androidEvidenceBinaryStage",
    "binaryReceipt": "androidEvidenceBinaryReceipt",
    "compatibilityRequest": "androidEvidenceCompatibilityRequest",
    "binaryContractEvidence": "androidEvidenceBinaryContractEvidence",
}
CONTROL_FILES = {"apk-execution.json", "apk-build.log", "binary-receipt.json", "package-receipt.json"}


SOURCE_CHECK_SCOPE = "sdk-android-source-checks-v1"
SOURCE_CHECKS = {
    "test": (":codex-agent-runtime-android:testDebugUnitTest",
             "codex-agent-runtime-android/build/test-results/**/*.xml", "test-report"),
    "metadata": (":codex-agent-runtime-android:lintRelease",
                 "codex-agent-runtime-android/build/reports/lint-results-release.xml", "lint-report"),
}


def _check_tasks(value):
    return [task for action, (task, _, _) in SOURCE_CHECKS.items()
            if value["lanes"]["android"][action]]


def _check_source_checks(plan, directory, producer):
    value = _authorized_plan(plan)
    directory = Path(directory)
    raw = read_regular_file_bytes(directory / "source-checks.json", reject_symlink_parents=True)
    report = load_canonical_json_bytes(raw)
    expected_inputs = {name: sha256_bytes(read_regular_file_bytes(
        plan.parent / "inventories/android" / name, reject_symlink_parents=True))
        for name in INPUT_NAMES.values()}
    if (set(report) != {"schemaVersion", "kind", "producer", "planSha256", "inputs", "tasks", "exitCode", "reports"}
            or report["schemaVersion"] != 1 or report["kind"] != SOURCE_CHECK_SCOPE
            or report["producer"] != producer or report["tasks"] != _check_tasks(value)
            or type(report["exitCode"]) is not int or report["exitCode"] != 0
            or report["planSha256"] != sha256_bytes(read_regular_file_bytes(plan, reject_symlink_parents=True))
            or report["inputs"] != expected_inputs):
        raise ValueError("Android source checks differ from the selected original plan, producer or tasks")
    inventory = [row for row in regular_file_inventory(directory, allow_empty=True)
                 if row["relativePath"] not in {"lane-receipt.json", *INPUT_NAMES.values()}]
    expected = [row for row in inventory if row["relativePath"] != "source-checks.json"]
    if report["reports"] != expected:
        raise ValueError("Android source-check reports differ from their exact inventory")
    if any(row["bytes"] == 0 and row["relativePath"] != "source-checks.log" for row in expected):
        raise ValueError("Android source-check report is empty")
    paths = {row["relativePath"] for row in expected}
    allowed = {"source-checks.log"}
    for action, (_, pattern, _) in SOURCE_CHECKS.items():
        matches = {p.relative_to(directory).as_posix() for p in directory.glob(pattern)}
        if bool(matches) != bool(value["lanes"]["android"][action]):
            raise ValueError("Android source checks lack exactly the selected unit/lint reports")
        allowed.update(matches)
    if paths != allowed:
        raise ValueError("Android source-check transport has missing or unexpected files")
    return report, inventory


def source_checks(root, plan, destination):
    """Execute only genuine selected source tests/lint, never APK or product tasks."""
    require_no_signing_secret(os.environ)
    root, plan, destination = Path(root).resolve(strict=True), Path(plan).absolute(), Path(destination).absolute()
    _require_capability_output_separate(destination, (root, plan))
    if destination.exists() or destination.is_symlink():
        raise ValueError("Android source-check destination must be fresh")
    value = products._validate_plan(plan, root)
    _authorized_plan(plan)
    producer = products.validate_producer(products._consumer(value, os.environ)["producer"])
    products._runtime_worker_checkout(root, producer)
    inputs = [plan, *(plan.parent / "inventories/android" / name for name in INPUT_NAMES.values())]
    before = {p: read_regular_file_bytes(p, reject_symlink_parents=True) for p in inputs}
    tasks = _check_tasks(value)
    with tempfile.TemporaryDirectory(prefix="android-source-checks-") as temporary:
        prepared = Path(temporary).resolve()
        with (prepared / "source-checks.log").open("wb") as log:
            if tasks:
                subprocess.run([str(root / "gradlew"), *tasks, "--build-cache", "--parallel", "--stacktrace",
                    "-PcodexAgent.candidateCommit=" + producer["commit"],
                    "-PcodexAgent.candidateTree=" + producer["tree"]], cwd=root,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, check=True)
        for action, (_, pattern, _) in SOURCE_CHECKS.items():
            if not value["lanes"]["android"][action]:
                continue
            matches = sorted(root.glob(pattern))
            if not matches:
                raise ValueError("Successful Android source check did not produce its selected report")
            for path in matches:
                target = prepared / path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(read_regular_file_bytes(path, reject_symlink_parents=True))
        report = {"schemaVersion": 1, "kind": SOURCE_CHECK_SCOPE, "producer": producer,
                  "planSha256": sha256_bytes(before[plan]),
                  "inputs": {name: sha256_bytes(before[plan.parent / "inventories/android" / name])
                             for name in INPUT_NAMES.values()},
                  "tasks": tasks, "exitCode": 0, "reports": regular_file_inventory(prepared, allow_empty=True)}
        write_canonical_json(prepared / "source-checks.json", report)
        _check_source_checks(plan, prepared, producer)
        products._runtime_worker_checkout(root, producer)
        if any(read_regular_file_bytes(p, reject_symlink_parents=True) != raw for p, raw in before.items()):
            raise ValueError("Android source-check controls changed during execution")
        java = subprocess.check_output([str(Path(os.environ["JAVA_HOME"]) / "bin/java"), "-version"],
                                       stderr=subprocess.STDOUT, text=True).strip()
        paths = [row["relativePath"] for row in regular_file_inventory(prepared, allow_empty=True)]
        actions = sorted(action for action in SOURCE_CHECKS if value["lanes"]["android"][action])
        create_receipt(argparse.Namespace(plan=plan, lane="android", output=prepared,
            workflow_path=producer["workflowPath"],
            artifact_name="codex-agent-ci-android-source-checks-" + producer["tree"],
            run_id=producer["runId"], run_attempt=producer["runAttempt"],
            runner=["os=" + os.environ["RUNNER_OS"], "arch=" + os.environ["RUNNER_ARCH"]],
            toolchain=["java=" + java, "evidenceScope=" + SOURCE_CHECK_SCOPE,
                       "validationActions=" + ",".join(actions)],
            artifact=[], evidence=[path + "=android-source-check" for path in paths]))
        validate_receipt(prepared / "lane-receipt.json", plan, prepared, "android",
                         categories=("test", "metadata"))
        publish_regular_tree(prepared, destination, allow_empty=True)
        products._runtime_worker_checkout(root, producer)
        if any(read_regular_file_bytes(p, reject_symlink_parents=True) != raw for p, raw in before.items()):
            raise ValueError("Android source-check controls changed before return")

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
    init_script = diagnostics / "contract-repository.init.gradle"
    init_script.write_text(CONTRACT_ANDROID_INIT, encoding="utf-8")
    argv += ["--init-script", str(init_script)]
    # Complete receipt controls before any compiler starts, even for compact
    # routing carriers. The shared policy projects these from authenticated Git.
    paths = [plan, *(plan.parent / "inventories/android" / name for name in INPUT_NAMES.values()),
             *map(Path, policy.values())]
    before = {p: regular_file_inventory(p) if p.is_dir() else read_regular_file_bytes(p, reject_symlink_parents=True)
              for p in paths}

    def unchanged():
        require_no_signing_secret(os.environ)
        if read_regular_file_bytes(init_script, reject_symlink_parents=True) != CONTRACT_ANDROID_INIT.encode():
            raise ValueError("APK consumer repository policy changed")
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
            "repositoryPolicySha256": sha256_bytes(CONTRACT_ANDROID_INIT.encode()),
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



_CONTRIBUTION_KIND = "sdk-android-current-contribution"
_CONTRIBUTION_FILE = "android-contribution.json"
_CONTRIBUTION_LIMIT = 1024 * 1024
_ANDROID_V = products.PhaseInstanceId("sdk", "sdk-android", "validation", "android")
_ANDROID_P = products.PhaseInstanceId("sdk", "sdk-android", "package", "android")


def _validate_android_contribution(value, consumer, plan_sha256):
    """Structural binding only; caller must authenticate the successful producer job."""
    from products.inventory import require_exact_keys
    from products.plan import _upstream_record
    from products.receipt import validate_phase_receipt, output_inventory_digest
    from products.sdk_android_validation_content import validate_android_validation_content
    value = require_exact_keys(value, {"schemaVersion", "kind", "result", "consumer",
        "planSha256", "validation", "package", "validationContent"}, "Android contribution")
    if (type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
            or value["kind"] != _CONTRIBUTION_KIND or value["result"] != "passed"
            or products.validate_producer(value["consumer"]) != consumer
            or value["planSha256"] != plan_sha256):
        raise ValueError("Android contribution differs from the current consumer or original plan")
    receipts = {}
    for name, identity in (("validation", _ANDROID_V), ("package", _ANDROID_P)):
        row = require_exact_keys(value[name], {"buildKey", "receiptSha256", "objectSha256", "receipt"},
                                 "Android original contribution")
        receipt = validate_phase_receipt(row["receipt"])
        if (products._identity(receipt) != identity or receipt["buildKey"] != row["buildKey"]
                or sha256_bytes(canonical_json_bytes(receipt)) != row["receiptSha256"]):
            raise ValueError("Android contribution changes its original receipt identity")
        require_sha256(row["objectSha256"], "Android original object")
        receipts[name] = receipt
    validation, package = receipts["validation"], receipts["package"]
    upstream = [row for row in validation["inputs"]["upstreamArtifacts"]
                if products._identity(row) == _ANDROID_P]
    content = validate_android_validation_content(value["validationContent"])
    raw = canonical_json_bytes(content)
    if (upstream != [_upstream_record(package)]
            or content["sdkVersion"] != validation["productVersion"]
            or package["productVersion"] != validation["productVersion"]
            or content["packageOutputsDigest"] != output_inventory_digest(package["outputs"])
            or validation["outputs"] != [{"kind": "android-validation-content",
                "relativePath": "outputs/validation/android-validation.json",
                "bytes": len(raw), "sha256": sha256_bytes(raw)}]):
        raise ValueError("Android contribution differs from the original P/V dependency or content")
    return value


def retained_android_contribution(state, plan_path, *, environ):
    """Consume the fixed V object inside completion's existing live verified state."""
    from reuse_qualification import CompletedFrozenReuse
    if type(state) is not products._VerifiedProductState or type(state.completed_frozen) is not CompletedFrozenReuse:
        raise ValueError("Android contribution requires the concrete live native state")
    plan_path = Path(plan_path).absolute()
    plan_raw = read_regular_file_bytes(plan_path, reject_symlink_parents=True)
    if load_json_bytes(plan_raw) != state.plan:
        raise ValueError("Android contribution plan differs from its verified state")
    current = products.validate_producer(products._consumer(state.plan, environ)["producer"])
    native = state.completed_frozen
    consumer = {"kind": "ci", "producer": current}
    native.check_consumer(consumer)
    originals = {}
    for name, identity in (("validation", _ANDROID_V), ("package", _ANDROID_P)):
        record = state.prior_carrier_phases.get(identity)
        if identity not in state.closure or record is None:
            raise ValueError("Android contribution is outside the original selected closure")
        envelope = native.envelope(record)
        if envelope is None:
            raise ValueError("Android contribution lacks its exact native original")
        originals[name] = {key: record[key] for key in ("buildKey", "receiptSha256", "objectSha256")}
        originals[name]["receipt"] = envelope["receipt"]
    with tempfile.TemporaryDirectory(prefix="android-qualified-validation-") as temporary:
        root = Path(temporary).resolve()
        restored = products._restore_product_objects(state, (_ANDROID_V,), root)[_ANDROID_V]
        if (restored["receiptBytes"] != canonical_json_bytes(originals["validation"]["receipt"])
                or restored["receipt"] != originals["validation"]["receipt"]):
            raise ValueError("Android materialization substituted the original validation receipt")
        path = root / "sdk-sdk-android-validation-android/stage/outputs/validation/android-validation.json"
        raw = read_regular_file_bytes(path, max_bytes=_CONTRIBUTION_LIMIT, reject_symlink_parents=True)
        value = {"schemaVersion": 1, "kind": _CONTRIBUTION_KIND, "result": "passed",
            "consumer": current, "planSha256": sha256_bytes(plan_raw), **originals,
            "validationContent": load_canonical_json_bytes(raw)}
        _validate_android_contribution(value, current, sha256_bytes(plan_raw))
        native.check_consumer(consumer)
        for name, identity in (("validation", _ANDROID_V), ("package", _ANDROID_P)):
            envelope = native.envelope(state.prior_carrier_phases[identity])
            if envelope is None or envelope["receipt"] != originals[name]["receipt"]:
                raise ValueError("Android native original changed during consumption")
        if read_regular_file_bytes(plan_path, reject_symlink_parents=True) != plan_raw or \
                products._consumer(state.plan, environ)["producer"] != current or \
                read_regular_file_bytes(path, reject_symlink_parents=True) != raw:
            raise ValueError("Android contribution inputs changed during consumption")
    return value


def observed_android_contribution(plan, *, repository_root, trusted_workflow_sha,
        artifact_id, artifact_sha256, contribution_sha256, environ):
    """Authenticate a bounded original SDK completion output, never a caller verdict."""
    from products.restore import verification_session
    require_no_signing_secret(environ)
    if (environ.get("GITHUB_ACTIONS") != "true" or environ.get("GITHUB_JOB") != "merge-gate"
            or not environ.get("GITHUB_TOKEN")):
        raise ValueError("Android contribution requires the actual merge-gate consumer")
    root, plan = Path(repository_root).resolve(strict=True), Path(plan).absolute()
    plan_raw = read_regular_file_bytes(plan, reject_symlink_parents=True)
    value = products._validate_plan(plan, root)
    if not validate_remote_build_authorization(value)[0] or value["mergeReady"] is not True:
        raise ValueError("Android contribution requires an authorized merge-ready plan")
    producer = products.validate_producer(products._consumer(value, environ)["producer"])
    if any(environ.get(key) != producer[field] for key, field in (
            ("GITHUB_REPOSITORY", "repository"), ("GITHUB_EVENT_NAME", "event"), ("GITHUB_SHA", "commit"))):
        raise ValueError("Android contribution environment differs from its current plan")
    require_sha256(contribution_sha256, "Android contribution digest")
    require_sha256(artifact_sha256, "Android contribution upload digest")
    require_integer(artifact_id, "Android contribution upload ID", 1)
    token = environ["GITHUB_TOKEN"]
    job = "product-validation / sdk-completion"
    with verification_session(), products._ci_observation_batch(
            (str(producer["runId"]), str(producer["runAttempt"])), share_nested=True):
        observed, = products._observe_ci_producer_jobs({"completion": producer}, jobs_by_phase={"completion": job},
            token=token, trusted_workflows_by_phase={"completion": {
                "path": ".github/workflows/product-validation.yml", "sha": trusted_workflow_sha}})
        artifact = products._contract_ci_upload_metadata(artifact_id, artifact_sha256,
            f"codex-agent-sdk-android-contribution-{producer['tree']}-attempt-{producer['runAttempt']}",
            producer, observed["run"], token)
        products._require_artifact_job_window(observed, job, artifact)
        size = require_integer(artifact["size_in_bytes"], "Android contribution upload bytes", 1)
        if size > _CONTRIBUTION_LIMIT:
            raise ValueError("Android contribution upload exceeds its bound")
        with tempfile.TemporaryDirectory(prefix="android-contribution-upload-") as temporary:
            archive = Path(temporary).resolve() / "contribution.zip"
            products._reuse_contract_ci_upload(artifact, producer, observed["run"], token,
                destination=archive, limit=_CONTRIBUTION_LIMIT, artifact_sha256=artifact_sha256, size=size)
            inventory, retained, transport = verified_zip_contents(archive,
                max_archive_bytes=_CONTRIBUTION_LIMIT, max_members=1, max_entry_bytes=_CONTRIBUTION_LIMIT,
                max_total_bytes=_CONTRIBUTION_LIMIT, retained_paths=(_CONTRIBUTION_FILE,),
                max_retained_bytes=_CONTRIBUTION_LIMIT, require_sorted=False)
            raw = retained.get(_CONTRIBUTION_FILE, b"")
            if (transport != {"bytes": size, "sha256": artifact_sha256}
                    or inventory != [{"relativePath": _CONTRIBUTION_FILE, "bytes": len(raw),
                                      "sha256": contribution_sha256}]
                    or retained != {_CONTRIBUTION_FILE: raw}):
                raise ValueError("Android contribution differs from its exact original upload")
            contribution = _validate_android_contribution(load_canonical_json_bytes(raw), producer, sha256_bytes(plan_raw))
        if (read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_raw
                or products._consumer(value, environ)["producer"] != producer
                or products._git_value(root, "rev-parse", "HEAD^{commit}") != producer["commit"]
                or products._git_value(root, "rev-parse", "HEAD^{tree}") != producer["tree"]):
            raise ValueError("Android contribution consumer or plan changed during observation")
    return contribution


def aggregate_retained_android(plan, receipts, destination, *, repository_root,
        trusted_workflow_sha, artifact_id, artifact_sha256, contribution_sha256,
        environ, auxiliary_contracts=False):
    """Combine current checks with an observed native contribution; never schema1 reuse."""
    from receipt import required_lanes, parse_validation_actions
    plan, receipts, destination = map(Path, (plan, receipts, destination))
    _require_capability_output_separate(destination, (plan, receipts))
    if destination.exists() or destination.is_symlink():
        raise ValueError("Current Android gate destination must be fresh")
    plan_raw = read_regular_file_bytes(plan, reject_symlink_parents=True)
    selected = _authorized_plan(plan)
    required = required_lanes(selected)
    if "android" not in required:
        raise ValueError("Android contribution cannot add an unselected legacy lane")
    contribution = observed_android_contribution(plan, repository_root=repository_root,
        trusted_workflow_sha=trusted_workflow_sha, artifact_id=artifact_id,
        artifact_sha256=artifact_sha256, contribution_sha256=contribution_sha256, environ=environ)
    originals, controls = {}, {}
    for path in receipts.rglob("lane-receipt.json"):
        raw = read_regular_file_bytes(path, reject_symlink_parents=True)
        lane = load_json_bytes(raw).get("lane")
        value = validate_receipt(path, plan, path.parent, allow_compatible=lane != "android",
            **({"categories": ("test", "metadata")} if lane == "android" else {}))
        if lane in originals:
            raise ValueError("Duplicate current Android gate lane receipt")
        if lane == "android":
            producer = products.validate_producer({
                **{key: value[key] for key in ("repository", "workflowPath", "event", "runId", "runAttempt", "pullRequest")},
                "commit": value["validationCommit"], "tree": value["validationTree"]})
            if (producer != contribution["consumer"]
                    or value["toolchain"].get("evidenceScope") != SOURCE_CHECK_SCOPE
                    or parse_validation_actions(value["toolchain"]) != frozenset(
                        action for action in ("test", "metadata") if selected["lanes"]["android"][action])
                    or any(row["kind"] == "firebase-runtime-evidence" for row in value["evidence"])):
                raise ValueError("Android source receipt may claim only its actual current unit/lint checks")
            _check_source_checks(plan, path.parent, producer)
        originals[lane] = value
        controls[path] = raw
    expected = set(required)
    if auxiliary_contracts:
        auxiliary = originals.get("contracts")
        if ("contracts" in expected or auxiliary is None
                or not {"build", "test"}.issubset(parse_validation_actions(auxiliary["toolchain"]))
                or any(row["kind"] == "transport-provenance" for row in auxiliary["evidence"])):
            raise ValueError("Auxiliary tooling requires its original unselected contracts receipt")
        expected.add("contracts")
    if set(originals) != expected:
        raise ValueError("Current Android gate has missing or unexpected selected lane receipts")
    result = {"schemaVersion": 1, "kind": "current-validation-contributions", "result": "passed",
        "consumer": contribution["consumer"], "planSha256": sha256_bytes(plan_raw),
        "android": {"artifactId": artifact_id, "artifactSha256": artifact_sha256,
                    "contributionSha256": contribution_sha256, "original": contribution},
        "laneReceipts": {lane: sha256_bytes(canonical_json_bytes(value)) for lane, value in sorted(originals.items())}}
    if read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_raw or any(
            read_regular_file_bytes(path, reject_symlink_parents=True) != raw for path, raw in controls.items()):
        raise ValueError("Current validation controls changed before publication")
    with tempfile.TemporaryDirectory(prefix="android-current-gate-") as temporary:
        staged = Path(temporary).resolve()
        write_canonical_json(staged / "current-validation-contributions.json", result)
        publish_regular_tree(staged, destination)
    return result

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
