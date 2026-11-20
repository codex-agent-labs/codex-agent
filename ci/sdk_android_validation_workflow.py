"""Compose elected Android validation from existing authenticated gates.

This controller does not execute Firebase, mint host trust, sign content, or
grant family admission.  Caller-supplied originals and both official captures
remain external authority that the existing full gates must authenticate.
"""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import tempfile

if __package__:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, read_regular_file_bytes,
    publish_regular_tree, regular_file_inventory, snapshot_regular_tree, write_canonical_json,
    verified_zip_contents,
)
from products.registry import PhaseInstanceId
from products.restore import verification_scoped
from products.sdk_apple_validation_admission import apple_validation_policy_arguments
from products.sdk_inputs import stage_sdk_inputs
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.signatures import load_keyring, public_key_path
from products.signing_isolation import require_no_signing_secret
from sdk_android_evidence_capture import capture_android_evidence, _INSTALLED, _validate_installed_controls, _CONTRIBUTION_LIMIT
from sdk_android_firebase_capture import capture_android_firebase_evidence, _producer_from_receipt
from sdk_android_upload_locator import (retained_android_evidence_origin, capture_retained_android_plan,
    require_retained_android_authority, require_retained_android_capture)
from products import sdk_android_validation_phase as validation_phase
from sdk_phase import maven_consumed_predecessors


_INSTANCE = PhaseInstanceId("sdk", "sdk-android", "validation", "android")
_LIMIT = 512 * 1024 * 1024

_CONSUMER_INPUTS = (
    PhaseInstanceId("contract", "contract", "binary", "common"),
    PhaseInstanceId("sdk", "sdk-core", "package", "common"),
    PhaseInstanceId("sdk", "sdk-android", "package", "android"),
)


_RUNTIME_MAVEN = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
_IOS_PACKAGE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
_INSTALLED_CONSUMERS = {lane: values[:3] for lane, values in _INSTALLED.items()}

_RUNTIME_COMPONENTS = {
    "desktop": ("jvm", "macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64"),
    "node-js": ("node-js",), "node-wasm": ("node-wasm",),
}
_CONSUMER_TEMPLATE = ".github/actions/run-ci-lane/installed-consumer"
_TEMPLATE_FILES = (
    "settings.gradle.kts", "src/commonMain/kotlin/Consumer.kt",
    "src/androidMain/kotlin/AndroidConsumer.kt",
    "src/androidMain/java/io/github/codex_agent_labs/codexagent/stagedconsumer/AndroidJavaConsumer.java",
    "src/desktopMain/kotlin/DesktopConsumer.kt",
    "src/desktopMain/java/io/github/codex_agent_labs/codexagent/stagedconsumer/DesktopJavaConsumer.java",
    "src/iosMain/kotlin/IosConsumer.kt", "src/jsMain/kotlin/NodeConsumer.kt",
)


def _copy_retained_ios_maven(state, record, destination, target, stack, *, token):
    """Stream only native-bound Maven leaves; unread object bytes grant no proof."""
    from completed_sdk_reuse import original_worker_member
    from runtime_reference_archive import open_reference_archive, open_stored_reference_archive, copy_reference_member
    native = state.completed_frozen
    envelope = native.envelope(record)
    if envelope is None or not token:
        raise ValueError("Installed iOS consumer requires its live original and observation token")
    receipt = envelope["receipt"]
    if receipt["productVersion"] != state.expected_fixed["versions"]["sdk"]:
        raise ValueError("Installed iOS input differs from its native original receipt")
    child = {"ios-device": "iosarm64", "ios-simulator": "iossimulatorarm64"}.get(target)
    if child is None:
        raise ValueError("Unsupported installed iOS consumer target")
    prefix = "outputs/maven/io/github/codex-agent-labs/"
    gavs = ("codex-agent-runtime-ios", "codex-agent-runtime-ios-" + child)
    outputs = [row for row in receipt["outputs"] if row["kind"] == "maven"
               and any(row["relativePath"].startswith(prefix + gav + "/") for gav in gavs)]
    if any(not any(row["relativePath"].startswith(prefix + gav + "/") for row in outputs) for gav in gavs):
        raise ValueError("Installed iOS Maven input lacks its root or selected target")
    extension = native.sdk_extension()
    if extension is None or not original_worker_member(extension["spec"]):
        raise ValueError("Installed iOS Maven input requires the qualified original worker member")
    members = [row for row in extension["proof"]["members"] if row["sha256"] == record["objectSha256"]]
    if len(members) != 1:
        raise ValueError("Installed iOS original object member is missing or ambiguous")
    member = members[0]
    _, artifact, _ = native.observe_extended_sdk(record, producer=state.producer, token=token)
    archive, stream = stack.enter_context(open_reference_archive(
        artifact, token, **product_reuse._worker_upload_reference_limits(_IOS_PACKAGE)))
    nested = stack.enter_context(open_stored_reference_archive(
        archive, member["relativePath"], expected_bytes=member["bytes"]))
    for row in outputs:
        relative = row["relativePath"].removeprefix("outputs/maven/")
        file = destination / relative
        if file.exists() or file.is_symlink():
            raise ValueError("Installed consumer Maven inputs overlap")
        copy_reference_member(nested, "stage/" + row["relativePath"], file, row)
    product_reuse.count("installedIosMavenLogicalBytes", sum(row["bytes"] for row in outputs))
    if stream is not None:
        product_reuse.count("installedIosMavenOriginalRangeBytes", stream.transferred)

    def unchanged():
        if native.envelope(record) != envelope:
            raise ValueError("Installed iOS Maven native authority changed during use")
    stack.callback(unchanged)


def _installed_template(root, private, task, versions):
    """Select one fixed consumer-only declaration through the existing task property."""
    control = root / _CONSUMER_TEMPLATE
    source = root / "gradle/release/kmp-consumer-template"
    before = {name: _read(source / name) for name in _TEMPLATE_FILES}
    build_path = control / "build.gradle.kts" if task in {
        _INSTALLED_CONSUMERS["consumer-" + target][1] for target in _RUNTIME_COMPONENTS
    } else source / "build.gradle.kts"
    build = _read(build_path)
    init = _read(control / "target-template.init.gradle")
    template = private / "template"
    template.mkdir()
    for name, contents in before.items():
        output = template / name
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            stream.write(contents)
    (template / "build.gradle.kts").write_bytes(build)
    script = private / "target-template.init.gradle"
    text = init.decode("utf-8")
    for marker, value in (("__CODEX_TASK__", task), ("__CODEX_TEMPLATE__", str(template)),
                          ("__CODEX_INVENTORY__", "inventory" + task.removeprefix("verifyStagedKmpConsumer") + "ConsumerMavenRepository"),
                          ("__CODEX_SDK_VERSION__", versions["sdk"]),
                          ("__CODEX_RUNTIME_VERSION__", versions["runtime-release"]),
                          ("__CODEX_CONTRACT_VERSION__", versions["contract"])):
        if text.count(marker) != 1:
            raise ValueError("Fixed installed consumer template selector is malformed")
        text = text.replace(marker, json.dumps(value).replace("$", "\\$"))
    script.write_text(text, encoding="utf-8")
    prepared = regular_file_inventory(template)
    script_bytes = _read(script)

    def unchanged():
        if ({name: _read(source / name) for name in _TEMPLATE_FILES} != before
                or _read(build_path) != build
                or _read(control / "target-template.init.gradle") != init
                or regular_file_inventory(template) != prepared or _read(script) != script_bytes):
            raise ValueError("Installed consumer template inputs changed during use")
    return script, unchanged


def run_retained_android_consumer(state, *, plan_path, repository_root, environ):
    """Preserve the existing fixed Android entry point and its full consumer semantics."""
    return _run_retained_installed_consumer(state, lane="consumer-android", plan_path=plan_path,
        repository_root=repository_root, environ=environ, legacy_android_projection=True)


def run_retained_installed_consumer(state, *, lane, plan_path, repository_root, environ):
    """Return detached current controls; never project or forward the Maven inputs."""
    return _run_retained_installed_consumer(state, lane=lane, plan_path=plan_path,
        repository_root=repository_root, environ=environ, legacy_android_projection=False)


@product_reuse.measured
def _run_retained_installed_consumer(state, *, lane, plan_path, repository_root, environ,
                                   legacy_android_projection):
    """Consume one fixed lane inside the existing live replay owner, never caller evidence."""
    from reuse_qualification import CompletedFrozenReuse
    from products.contract_model import contract_maven_identity
    from runtime_reference_transport import ENVIRONMENT as authority_environment
    from runtime_reference_transport import _copy_exact
    from products.restore import memoized_file_inventory

    if lane not in _INSTALLED_CONSUMERS:
        raise ValueError("Unsupported installed consumer lane")
    target, task, extras = _INSTALLED_CONSUMERS[lane]
    if legacy_android_projection and lane != "consumer-android":
        raise ValueError("Legacy Maven projection is Android-only")
    instances = (*_CONSUMER_INPUTS[:2], *extras)
    require_no_signing_secret(environ)
    if (type(state) is not product_reuse._VerifiedProductState
            or type(state.completed_frozen) is not CompletedFrozenReuse):
        raise ValueError("Installed consumer requires live native replay authority")
    root = Path(repository_root).resolve(strict=True)
    plan_path = Path(plan_path).absolute()
    plan_bytes = _read(plan_path)
    if (load_json_bytes(plan_bytes) != state.plan
            or state.consumer != product_reuse._consumer(state.plan, environ)
            or environ.get("CI_VALIDATION_COMMIT") != state.plan["validationCommit"]
            or environ.get("CI_VALIDATION_TREE") != state.plan["validationTree"]
            or not any(state.plan["lanes"].get(lane, {}).get(key) is True
                       for key in ("build", "test", "metadata"))):
        raise ValueError("Installed consumer differs from its authorized lane")
    native = state.completed_frozen
    native.check_consumer(state.consumer)
    records = {}
    for instance in instances:
        record = state.prior_by_instance.get(instance)
        carrier = state.prior_carrier_phases.get(instance)
        if (record is None or carrier is None or record["state"] not in {"retained", "reused"}
                or any(record[key] != carrier[key] for key in (
                    "product", "component", "phase", "target", "buildKey", "receiptSha256", "objectSha256"))):
            raise ValueError("Installed consumer lacks an exact completed predecessor")
        records[instance] = record
    originals = canonical_json_bytes([records[instance] for instance in instances])
    product_reuse._runtime_worker_checkout(root, state.producer)
    with tempfile.TemporaryDirectory(prefix="sdk-installed-consumer-") as temporary:
        private = Path(temporary).resolve()
        predecessors = private / "predecessors"
        predecessors.mkdir()
        restored_instances = tuple(instance for instance in instances if instance != _IOS_PACKAGE)
        restored = product_reuse._restore_product_objects(state, restored_instances, predecessors)
        stages = {}
        for instance in restored_instances:
            original = restored[instance]
            envelope = native.envelope(records[instance], original["receiptBytes"])
            version = state.expected_fixed["versions"][
                "runtime-release" if instance.product == "runtime" else instance.product]
            if (envelope is None or envelope["receipt"] != original["receipt"]
                    or original["receipt"]["productVersion"] != version):
                raise ValueError("Installed consumer input differs from its native original receipt")
            stages[instance] = predecessors / "-".join((
                instance.product, instance.component, instance.phase, instance.target)) / "stage"
        before = regular_file_inventory(predecessors)
        maven = private / "maven"
        maven.mkdir()

        for instance in restored_instances:
            source = stages[instance] / "outputs/maven"
            roots = ([source / component for component in _RUNTIME_COMPONENTS[target]]
                     if instance == _RUNTIME_MAVEN else [source])
            for selected in roots:
                prefix = selected.relative_to(stages[instance]).as_posix() + "/"
                expected = sorted(({
                    "relativePath": row["relativePath"].removeprefix(prefix),
                    "bytes": row["bytes"], "sha256": row["sha256"],
                } for row in restored[instance]["receipt"]["outputs"]
                    if row["kind"] == "maven" and row["relativePath"].startswith(prefix)),
                    key=lambda row: row["relativePath"])
                captured_prefix = selected.relative_to(predecessors).as_posix() + "/"
                captured = [{**row, "relativePath": row["relativePath"].removeprefix(captured_prefix)}
                            for row in before if row["relativePath"].startswith(captured_prefix)]
                if not expected or captured != expected:
                    raise ValueError("Installed consumer Maven files differ from the native receipt")
                for row in expected:
                    if instance == _CONSUMER_INPUTS[0]:
                        contract_maven_identity("maven/" + row["relativePath"],
                            restored[instance]["receipt"]["productVersion"])
                    destination = maven / row["relativePath"]
                    if destination.exists() or destination.is_symlink():
                        raise ValueError("Installed consumer Maven inputs overlap")
                    _copy_exact(selected / row["relativePath"], destination, row)
        template_unchanged = lambda: None
        command = [str(root / "gradlew"), task, "--build-cache", "--parallel", "--stacktrace",
                   "-PcodexAgent.candidateCommit=" + state.plan["validationCommit"],
                   "-PcodexAgent.candidateTree=" + state.plan["validationTree"]]
        if not legacy_android_projection:
            script, template_unchanged = _installed_template(root, private, task, state.expected_fixed["versions"])
            command.extend(["--init-script", str(script)])
        command.append("-PcodexAgent.mavenRepositoryDirectory=" + str(maven))
        environment = {key: value for key, value in environ.items()
                       if key not in {"GITHUB_TOKEN", "GH_TOKEN", "REUSE_AUTHORITY_READ_TOKEN",
                                      *authority_environment}}
        report_root = root / "build/protected-candidate" / state.plan["validationCommit"] / "reports"
        report_path = report_root / f"kmp-consumer-{target}.json"
        inventory_path = report_root / f"maven-inventory-{target}.json"
        if not legacy_android_projection:
            for path in (report_path, inventory_path):
                if path.exists() or path.is_symlink():
                    raise ValueError("Installed consumer controls must be fresh")
        with ExitStack() as stack:
            if _IOS_PACKAGE in instances:
                _copy_retained_ios_maven(state, records[_IOS_PACKAGE], maven, target, stack,
                    token=environ.get("GITHUB_TOKEN", ""))
            maven_before = memoized_file_inventory(maven)

            def unchanged():
                require_no_signing_secret(environ)
                native.check_consumer(state.consumer)
                product_reuse._runtime_worker_checkout(root, state.producer)
                template_unchanged()
                if (_read(plan_path) != plan_bytes or regular_file_inventory(predecessors) != before
                        or memoized_file_inventory(maven) != maven_before
                        or canonical_json_bytes([state.prior_by_instance[instance]
                                                 for instance in instances]) != originals):
                    raise ValueError("Installed consumer inputs changed during use")

            unchanged()
            try:
                subprocess.run(command, cwd=root, env=environment, stdin=subprocess.DEVNULL, check=True)
            finally:
                unchanged()
        if legacy_android_projection:
            projection = root / "build/protected-candidate" / state.plan["validationCommit"] / "consumer-maven/android"
            publish_regular_tree(maven, projection, expected_inventory=maven_before)
            product_reuse.count("androidInstalledMavenProjectionTrees")
            product_reuse.count("androidInstalledMavenProjectionBytes", sum(row["bytes"] for row in maven_before))
            unchanged()
            return None
        controls = _installed_consumer_controls(state, lane, target, task, instances,
            plan_bytes, maven_before, report_path, inventory_path)
        unchanged()
        return controls



def _installed_consumer_controls(state, lane, target, task, instances, plan_bytes,
                                 maven_files, report_path, inventory_path):
    """Check the unchanged task's two small formats; this value grants no authority."""
    from products.inventory import sha256_bytes
    raw_report, raw_inventory = (read_regular_file_bytes(path, max_bytes=_CONTRIBUTION_LIMIT,
        reject_symlink_parents=True) for path in (report_path, inventory_path))
    fields = ("product", "component", "phase", "target", "buildKey", "receiptSha256", "objectSha256")
    record = {"schemaVersion": 1, "kind": "installed-consumer-validation",
        "producer": state.consumer["producer"], "planSha256": sha256_bytes(plan_bytes),
        "lane": lane, "target": target, "task": task,
        "originalInputs": [{key: state.prior_by_instance[instance][key] for key in fields} for instance in instances],
        "mavenFiles": maven_files, "mavenInventorySha256": sha256_bytes(raw_inventory),
        "consumerReportSha256": sha256_bytes(raw_report)}
    # One fixed validator serves both the producer and its independent observer.
    # It receives the live caller's expected tuples/files, never serialized authority.
    detached = _validate_installed_controls({"installed-consumer.json": canonical_json_bytes(record),
        f"kmp-consumer-{target}.json": raw_report, f"maven-inventory-{target}.json": raw_inventory},
        state.consumer["producer"], sha256_bytes(plan_bytes), lane, state.prior_by_instance,
        state.expected_fixed["versions"])
    return {"record": detached, "consumerReport": raw_report, "mavenInventory": raw_inventory}


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _retain_original_inputs(request, evidence, destination):
    """Retain public replay inputs; caller authentication remains external."""
    original_request = destination / "original-compatibility-request.json"
    original_request.parent.mkdir(parents=True)
    original_request.write_bytes(_read(request))
    stage_sdk_inputs(original_request, destination / "sdk-inputs",
                     request_directory=Path(request).parent)
    if _read(original_request) != _read(request):
        raise ValueError("Retained Android compatibility request differs from its exact original")

    trees, files = validation_phase._contract_sources(evidence)
    captured = {
        "stageRoot": destination / "contract/stage",
        "phaseReceipt": destination / "contract/phase-receipt.json",
        "attestation": destination / "contract/auth/attestation" / Path(evidence["attestation"]).name,
        "attestationSignature": destination / "contract/auth/signature" /
            Path(evidence["attestationSignature"]).name,
        "publicKey": destination / "contract/auth/public-key" / Path(evidence["publicKey"]).name,
    }
    snapshot_regular_tree(trees["contract/stage"], captured["stageRoot"], allow_empty=True)
    snapshot_regular_tree(trees["contract/closure"],
        captured["attestation"].parent / validation_phase.CONTRACT_EXECUTION_CLOSURE_DIRECTORY,
        allow_empty=True)
    for field in ("phaseReceipt", "attestation", "attestationSignature", "publicKey"):
        source, target = files["contract/" + field], captured[field]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_read(source))
    public_keys = {}
    if evidence["keyring"] is not None:
        captured["keyring"] = destination / "contract/trust" / Path(evidence["keyring"]).name
        captured["keyring"].parent.mkdir(parents=True)
        captured["keyring"].write_bytes(_read(files["contract/keyring"]))
        keyring = load_keyring(captured["keyring"], Path(evidence["keysDirectory"]))
        keys = destination / "contract/trust/keys"
        keys.mkdir(parents=True)
        for record in ([keyring["activeKey"]] if keyring["activeKey"] else []) + keyring["retiredKeys"]:
            source = public_key_path(Path(evidence["keysDirectory"]), record["keyId"])
            public_keys[source] = _read(source)
            (keys / source.name).write_bytes(public_keys[source])
        captured["keysDirectory"] = keys
    relocated = {name: (value if name == "expectedTrustDomain" or value is None else str(captured[name]))
                 for name, value in evidence.items()}
    retained_trees, retained_files = validation_phase._contract_sources(relocated)
    if (any(regular_file_inventory(retained_trees[name], allow_empty=True) !=
            regular_file_inventory(source, allow_empty=True) for name, source in trees.items()
            if name != "contract/keys")
            or any(_read(retained_files[name]) != _read(source) for name, source in files.items())
            or any(_read(source) != raw or _read(captured["keysDirectory"] / source.name) != raw
                   for source, raw in public_keys.items())):
        raise ValueError("Retained Android Contract evidence differs from its exact original")
    write_canonical_json(destination / "binary-contract-invocation.json", relocated)


@verification_scoped
def execute(
    plan: Path, discovery: Path, state: Path, destination: Path, *,
    expected_build_key: str,
    package_stage: Path, package_receipt: Path,
    binary_stage: Path, binary_receipt: Path,
    compatibility_request: Path, binary_contract_evidence: dict,
    trusted_workflow_sha: str, trusted_android_workflow_sha: str,
    trusted_source_commit: str, trusted_source_tree: str,
    tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, apkanalyzer_executable: Path,
    policy_revision: str, required_trust_domain: str,
    repository_root: Path, environ: dict, token: str,
    tooling_keyring: Path | None = None,
    tooling_keys_directory: Path | None = None,
    sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None,
    sdk_android_metadata_admission=None,
    completed_frozen=None,
) -> dict:
    """Finalize one elected Android validation only after all original checks."""
    require_no_signing_secret(environ)
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Android tooling keyring and directory must be supplied together")
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK Android validation destination must not exist")

    plan = Path(plan).absolute()
    package_stage, binary_stage = Path(package_stage).absolute(), Path(binary_stage).absolute()
    package_receipt, binary_receipt = Path(package_receipt).absolute(), Path(binary_receipt).absolute()
    compatibility_request = Path(compatibility_request).absolute()
    tooling_evidence, tooling_public_key = Path(tooling_evidence).absolute(), Path(tooling_public_key).absolute()
    java_executable, apkanalyzer_executable = Path(java_executable).absolute(), Path(apkanalyzer_executable).absolute()
    plan_bytes = _read(plan)
    trees = {"discovery": discovery, "state": state, "package": package_stage,
             "binary": binary_stage, "tooling": tooling_evidence}
    files = {"packageReceipt": package_receipt, "binaryReceipt": binary_receipt,
             "compatibilityRequest": compatibility_request,
             "toolingPublicKey": tooling_public_key, "java": java_executable,
             "apkanalyzer": apkanalyzer_executable}
    contract_trees, contract_files = validation_phase._contract_sources(binary_contract_evidence)
    trees.update(contract_trees)
    files.update(contract_files)
    if sdk_apple_validation_policy is not None:
        for name, path in apple_validation_policy_arguments(sdk_apple_validation_policy).items():
            if isinstance(path, Path):
                (trees if path.is_dir() else files)["applePolicy/" + name] = path
    if tooling_keyring is not None:
        files["toolingKeyring"] = Path(tooling_keyring)
        trees["toolingKeysDirectory"] = Path(tooling_keys_directory)
    compatibility_before = _request_inventory(compatibility_request)
    _require_capability_output_separate(
        destination, [plan, compatibility_request, *compatibility_before,
                      *trees.values(), *files.values()])
    tree_before = {name: regular_file_inventory(path, allow_empty=True)
                   for name, path in trees.items()}
    file_before = {name: _read(path) for name, path in files.items()}
    policy_before = canonical_json_bytes({
        "binaryContractEvidence": binary_contract_evidence,
        "trustedWorkflowSha": trusted_workflow_sha,
        "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
        "trustedSourceCommit": trusted_source_commit,
        "trustedSourceTree": trusted_source_tree,
        "policyRevision": policy_revision,
        "requiredTrustDomain": required_trust_domain,
        "sdkAppleValidationPolicy": sdk_apple_validation_policy,
    })
    retained = {}
    selected_inventory = None
    stage = destination / "stage"
    stage_inventory = None
    ready = producer = version = manifest = None

    def unchanged():
        require_no_signing_secret(environ)
        if (_read(plan) != plan_bytes
                or canonical_json_bytes({
                    "binaryContractEvidence": binary_contract_evidence,
                    "trustedWorkflowSha": trusted_workflow_sha,
                    "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
                    "trustedSourceCommit": trusted_source_commit,
                    "trustedSourceTree": trusted_source_tree,
                    "policyRevision": policy_revision,
                    "requiredTrustDomain": required_trust_domain,
                    "sdkAppleValidationPolicy": sdk_apple_validation_policy,
                }) != policy_before
                or any(regular_file_inventory(path, allow_empty=True) != tree_before[name]
                       for name, path in trees.items())
                or any(_read(path) != file_before[name] for name, path in files.items())
                or _request_inventory(compatibility_request) != compatibility_before
                or any(regular_file_inventory(path, allow_empty=True) != inventory
                       for path, inventory in retained.items())
                or (selected_inventory is not None and
                    regular_file_inventory(destination / "inputs", allow_empty=True) != selected_inventory)
                or (ready is not None and canonical_json_bytes(ready) !=
                    _read(destination / "inputs/phase-plan.json"))
                or (producer is not None and canonical_json_bytes(producer) !=
                    _read(destination / "inputs/producer.json"))
                or (stage_inventory is not None and
                    regular_file_inventory(stage) != stage_inventory)):
            raise ValueError("SDK Android validation original inputs or retained evidence changed")

    tooling = {
        "evidence": str(tooling_evidence), "publicKey": str(tooling_public_key),
        "javaExecutable": str(java_executable), "requiredTrustDomain": required_trust_domain,
        "keyring": str(Path(tooling_keyring).absolute()) if tooling_keyring is not None else None,
        "keysDirectory": str(Path(tooling_keys_directory).absolute()) if tooling_keys_directory is not None else None,
    }
    apple = ({} if sdk_apple_validation_policy is None else
             {"sdk_apple_validation_policy": sdk_apple_validation_policy})
    admissions = {name: value for name, value in (
        ("sdk_facade_metadata_admission", sdk_facade_metadata_admission),
        ("sdk_android_metadata_admission", sdk_android_metadata_admission),
    ) if value is not None}
    destination = product_reuse._prepare_destination(destination, root)
    ready = product_reuse.materialize_product_predecessors(
        plan, discovery, state, _INSTANCE, destination / "inputs",
        expected_build_key=expected_build_key, repository_root=root, environ=environ,
        materialized_scope=maven_consumed_predecessors(_INSTANCE),
        sdk_validation_tooling=tooling, sdk_original_workflow_sha=trusted_workflow_sha,
        **apple, **admissions,
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
    selected_inventory = regular_file_inventory(destination / "inputs", allow_empty=True)
    producer = product_reuse.validate_producer(product_reuse._canonical_control(
        destination / "inputs/producer.json", "Elected Android validation producer"))
    if _read(destination / "inputs/phase-plan.json") != canonical_json_bytes(ready):
        raise ValueError("Android validation retained election differs from its selected plan")

    def selected(phase):
        directory = destination / f"inputs/sdk-sdk-android-{phase}-android"
        receipt_path = directory / "phase-receipt.json"
        raw = _read(receipt_path)
        receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
        if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
                "sdk", "sdk-android", phase, "android"):
            raise ValueError("Android validation selected predecessor identity is invalid")
        manifest_value = product_reuse.verify_output_manifest_identity(
            directory / "stage", "sdk", "sdk-android", phase, "android", receipt["productVersion"])
        if manifest_value["outputs"] != receipt["outputs"]:
            raise ValueError("Android validation selected predecessor differs from its receipt")
        return directory / "stage", receipt, raw

    selected_package_stage, selected_package, selected_package_bytes = selected("package")
    selected_binary_stage, selected_binary, selected_binary_bytes = selected("binary")
    package = product_reuse.validate_phase_receipt(load_canonical_json_bytes(file_before["packageReceipt"]))
    binary = product_reuse.validate_phase_receipt(load_canonical_json_bytes(file_before["binaryReceipt"]))
    if (file_before["packageReceipt"] != selected_package_bytes
            or file_before["binaryReceipt"] != selected_binary_bytes
            or regular_file_inventory(package_stage) != regular_file_inventory(selected_package_stage)
            or regular_file_inventory(binary_stage) != regular_file_inventory(selected_binary_stage)):
        raise ValueError("Android caller package or binary differs from its elected original predecessor")
    if package != selected_package or binary != selected_binary:
        raise ValueError("Android caller package or binary receipt differs from its elected original")
    binary_producer = product_reuse.validate_producer(binary["producer"], "Android binary original producer")
    version = package["productVersion"]
    if binary["productVersion"] != version:
        raise ValueError("Android selected package and binary versions differ")
    unchanged()

    try:
        with tempfile.TemporaryDirectory(prefix="sdk-android-validation-captures-") as temporary:
            private = Path(temporary).resolve()
            private_final, private_protected = private / "final", private / "protected"
            origin = retained_android_evidence_origin(ready["buildKey"], producer)
            require_retained_android_authority(origin, trusted_source_commit=trusted_source_commit,
                trusted_source_tree=trusted_source_tree, trusted_android_workflow_sha=trusted_android_workflow_sha)
            capture_producer = producer if origin is None else origin["producer"]
            capture_plan, capture_environment, revision = plan, environ, {}
            capture_workflow = trusted_workflow_sha
            if origin is not None:
                capture_plan = capture_retained_android_plan(origin, root, private / "historical-plan", token=token)
                capture_environment = {**environ, "GITHUB_RUN_ID": str(capture_producer["runId"]),
                    "GITHUB_RUN_ATTEMPT": str(capture_producer["runAttempt"])}
                revision = {"expected_revision": capture_producer["commit"]}
                capture_workflow = origin["workflowSha"]
            final_transport = capture_android_evidence(
                capture_plan, root, private_final, trusted_workflow_sha=capture_workflow,
                trusted_android_workflow_sha=trusted_android_workflow_sha,
                environ=capture_environment, token=token, **revision)
            if final_transport.get("captureProducer") != capture_producer:
                raise ValueError("Android final capture differs from the elected producer")
            protected_transport = capture_android_firebase_evidence(
                capture_plan, root, private_final, private_protected,
                trusted_workflow_sha=capture_workflow,
                trusted_android_workflow_sha=trusted_android_workflow_sha,
                trusted_source_commit=trusted_source_commit,
                trusted_source_tree=trusted_source_tree, environ=capture_environment, token=token, **revision)
            if protected_transport.get("captureProducer") != capture_producer:
                raise ValueError("Android protected capture differs from the elected producer")
            require_retained_android_capture(origin, final_transport, protected_transport)
            private_inventories = {
                "final": regular_file_inventory(private_final, allow_empty=True),
                "protected": regular_file_inventory(private_protected, allow_empty=True),
            }
            originals = destination / "originals"
            for name, source in (("final", private_final), ("protected", private_protected)):
                target = originals / name
                snapshot_regular_tree(source, target, allow_empty=True)
                if regular_file_inventory(target, allow_empty=True) != private_inventories[name]:
                    raise ValueError("Android retained capture differs from its exact private original")
                retained[target] = private_inventories[name]
            _retain_original_inputs(compatibility_request, binary_contract_evidence,
                                    originals / "validation-inputs")
            retained[originals] = regular_file_inventory(originals, allow_empty=True)
            unchanged()
            manifest = validation_phase.produce_sdk_android_validation_phase(
                repository=root, package_stage=package_stage, package_receipt=package_receipt,
                binary_stage=binary_stage, binary_receipt=binary_receipt,
                compatibility_request=compatibility_request,
                binary_contract_evidence=binary_contract_evidence,
                final_capture=private_final, protected_capture=private_protected,
                expected_capture_producer=capture_producer,
                # The authenticated protected submission retains the APK's
                # original receipt even when Firebase/capture is retried.
                expected_original_producer=_producer_from_receipt(load_json_bytes(
                    _read(private_protected / "original/lane-receipt.json"))),
                expected_binary_producer=binary_producer,
                trusted_source_commit=trusted_source_commit, trusted_source_tree=trusted_source_tree,
                tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
                java_executable=java_executable, apkanalyzer_executable=apkanalyzer_executable,
                policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                destination=stage, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory)
            stage_inventory = regular_file_inventory(stage)
            if (regular_file_inventory(private_final, allow_empty=True) != private_inventories["final"]
                    or regular_file_inventory(private_protected, allow_empty=True) != private_inventories["protected"]):
                raise ValueError("Android private captures changed during full validation")
            unchanged()
    finally:
        unchanged()

    product_reuse._runtime_worker_checkout(root, producer)
    trust = "development" if producer["event"] == "pull_request" else "release"
    try:
        with tempfile.TemporaryDirectory(prefix="sdk-android-validation-candidate-") as temporary:
            candidate = Path(temporary).resolve() / "shard"
            shard = product_reuse.finalize_phase_object(
                stage_root=stage, phase_plan=ready, producer=producer,
                product_version=version, trust_domain=trust, destination=candidate)
            inventory = regular_file_inventory(candidate)
            if product_reuse.verify_phase_shard(candidate, _INSTANCE) != shard:
                raise ValueError("Android validation candidate differs from its finalized shard")
            unchanged()
            if regular_file_inventory(candidate) != inventory:
                raise ValueError("Android validation candidate changed before publication")
            publish_regular_tree(candidate, destination / "shard")
        if product_reuse.verify_phase_shard(destination / "shard", _INSTANCE) != shard:
            raise ValueError("Published Android validation shard differs from its private candidate")
    finally:
        unchanged()
    return {"stage": stage, "manifest": manifest, "shard": shard,
            "originals": destination / "originals"}


def main(argv=None) -> int:
    from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in (
        "plan", "destination",
        "package-stage", "package-receipt", "binary-stage", "binary-receipt",
        "compatibility-request", "binary-contract-evidence", "tooling-evidence",
        "tooling-public-key", "java-executable", "apkanalyzer-executable",
        "repository-root",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    for name in (
        "expected-build-key", "trusted-workflow-sha", "trusted-android-workflow-sha",
        "trusted-source-commit", "trusted-source-tree", "policy-revision",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    parser.add_argument("--tooling-keyring", type=Path)
    parser.add_argument("--tooling-keys-directory", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    add_completed_frozen_argument(parser)
    arguments = vars(parser.parse_args(argv))
    if (arguments["tooling_keyring"] is None) != (arguments["tooling_keys_directory"] is None):
        parser.error("Android tooling keyring and directory must be supplied together")
    try:
        with metadata_admission_options(arguments) as admissions, completed_frozen_options(arguments) as semantic:
            arguments["binary_contract_evidence"] = product_reuse._canonical_control(
                arguments["binary_contract_evidence"], "Caller Android binary Contract evidence")
            apple = arguments.pop("sdk_apple_validation_policy")
            if apple is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(
                    apple, "Caller Apple validation policy")
            execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""),
                    **admissions, **semantic)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
