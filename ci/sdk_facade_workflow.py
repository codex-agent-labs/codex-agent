"""Finalize elected Core validation after full original replay, never host admission."""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    snapshot_regular_tree, write_canonical_json,
)
from products.receipt import validate_producer, write_phase_receipt
from products.registry import PhaseInstanceId, SDK_FACADE_TARGETS
from products.sdk_facade_inputs import _request, _sources
from products.sdk_facade_native_policy import _TARGETS as _PINNED_NATIVE_TARGETS
from products.sdk_facade_validation import _inventory
from products.sdk_facade_validation_admission import (
    _context, _native_archive_path, _native_archive_digest, verify_sdk_facade_validation_original_content,
)
from products.sdk_inputs import REQUEST_NAME, stage_sdk_inputs
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.signatures import load_keyring, public_key_path
from products.signing_isolation import require_no_signing_secret
from sdk_facade_validation_phase import execute as execute_validation


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=512 * 1024 * 1024,
                                   reject_symlink_parents=True)


def _retain_request(request, value, destination):
    """Relocate invocation paths only; original evidence bytes are never rewritten."""
    _, trees, files = _sources(value)
    captured = {}
    for name, source in trees.items():
        if name.endswith("/keysDirectory"):
            continue  # Transport only named public keys, never unrelated/private files.
        target = destination / "trees" / name
        snapshot_regular_tree(source, target, allow_empty=True)
        captured[name] = target
    for name, source in files.items():
        target = destination / "files" / name / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_read(source))
        captured[name] = target
    for label in ("binaryContractEvidence", "validationContractEvidence"):
        snapshot_regular_tree(captured[label + "/closure"],
            captured[label + "/attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY)
        if value[label]["keysDirectory"] is not None:
            directory = Path(value[label]["keysDirectory"])
            keyring = load_keyring(captured[label + "/keyring"], directory)
            target = destination / "trees" / label / "keysDirectory"
            target.mkdir(parents=True)
            for record in ([keyring["activeKey"]] if keyring["activeKey"] else []) + keyring["retiredKeys"]:
                key = public_key_path(directory, record["keyId"])
                (target / key.name).write_bytes(_read(key))
            captured[label + "/keysDirectory"] = target
    stage_sdk_inputs(captured["compatibilityRequest"], destination / "compatibility",
                     request_directory=Path(value["compatibilityRequest"]).parent)
    relocated = dict(value)
    for name in ("packageStage", "packageReceipt", "binaryStage", "binaryReceipt"):
        relocated[name] = str(captured[name])
    relocated["compatibilityRequest"] = str(destination / "compatibility" / REQUEST_NAME)
    for label in ("binaryContractEvidence", "validationContractEvidence"):
        relocated[label] = {name: (member if name == "expectedTrustDomain" or member is None
                                   else str(captured[label + "/" + name]))
                            for name, member in value[label].items()}
    (destination / "original-request.json").write_bytes(_read(request))
    output = destination / "invocation-request.json"
    write_canonical_json(output, relocated)
    return output


def execute(plan, discovery, state, destination, *, target, expected_build_key,
            facade_request, android_sdk_directory, tooling_evidence, tooling_public_key,
            java_executable, policy_revision, required_trust_domain, repository_root,
            environ, consumer_java_executable=None, tooling_keyring=None,
            tooling_keys_directory=None, sdk_apple_validation_policy=None, native_compiler_archive=None):
    """Use existing election and full gates; retain external originals before receipt.

    Explicit caller paths/policy are not a downloaded request. Android SDK and
    Windows consumer Java context are independently supplied before execution;
    generated reports never choose their own expected command. This controller
    does not observe a hosted upload or grant catalog admission.
    """
    require_no_signing_secret(environ)
    if target not in SDK_FACADE_TARGETS:
        raise ValueError("Core validation requires an exact facade target")
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    if destination.exists() or destination.is_symlink() or destination.resolve(strict=False) != destination:
        raise ValueError("Core validation destination must be fresh and normalized")
    request = Path(facade_request).absolute()
    archive = _native_archive_path(target, native_compiler_archive)
    if archive is not None and target not in _PINNED_NATIVE_TARGETS:
        raise ValueError("Core native target has no supported pinned compiler archive policy")
    archive_digest = _native_archive_digest(archive) if archive is not None else None
    if archive is not None:
        _require_capability_output_separate(destination, [archive])
    value, request_bytes = _request(request)
    if value["target"] != target or Path(value["repository"]) != root:
        raise ValueError("Core request differs from its selected repository or target")
    _, trees, files = _sources(value)
    trees["tooling"] = Path(tooling_evidence)
    files.update({"plan": Path(plan), "request": request, "toolingPublicKey": Path(tooling_public_key),
                  "java": Path(java_executable)})
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Core tooling keyring and directory must be paired")
    if tooling_keyring is not None:
        files["toolingKeyring"] = Path(tooling_keyring)
        trees["toolingKeysDirectory"] = Path(tooling_keys_directory)
    if consumer_java_executable is not None:
        files["consumerJava"] = Path(consumer_java_executable)
    compatibility_before = _request_inventory(Path(value["compatibilityRequest"]))
    _require_capability_output_separate(destination, [*trees.values(), *files.values(), *compatibility_before])
    before_trees = {name: _inventory(path, allow_empty=True) for name, path in trees.items()}
    before_files = {name: _read(path) for name, path in files.items()}
    retained = {}

    def unchanged():
        require_no_signing_secret(environ)
        if (_read(request) != request_bytes
                or (archive is not None and _native_archive_digest(archive) != archive_digest)
                or any(_inventory(path, allow_empty=True) != before_trees[name] for name, path in trees.items())
                or any(_read(path) != before_files[name] for name, path in files.items())
                or _request_inventory(Path(value["compatibilityRequest"])) != compatibility_before
                or any(_inventory(path, allow_empty=True) != inventory for path, inventory in retained.items())):
            raise ValueError("Core validation elected inputs or retained evidence changed")

    tooling = {"evidence": str(Path(tooling_evidence).absolute()),
        "publicKey": str(Path(tooling_public_key).absolute()), "javaExecutable": str(Path(java_executable).absolute()),
        "requiredTrustDomain": required_trust_domain,
        "keyring": str(Path(tooling_keyring).absolute()) if tooling_keyring is not None else None,
        "keysDirectory": str(Path(tooling_keys_directory).absolute()) if tooling_keys_directory is not None else None}
    destination = product_reuse._prepare_destination(destination, root)
    try:
        inputs = destination / "inputs"
        ready = product_reuse.materialize_product_predecessors(
            Path(plan), discovery, state, PhaseInstanceId("sdk", "sdk-core", "validation", target), inputs,
            expected_build_key=expected_build_key, repository_root=root, environ=environ,
            sdk_validation_tooling=tooling, sdk_apple_validation_policy=sdk_apple_validation_policy)
        producer = validate_producer(load_canonical_json_bytes(_read(inputs / "producer.json")), "Core producer")
        if archive is not None:
            for output in (root / f"build/product-stage/sdk/sdk-core/validation/{target}",
                           root / f"build/imported-sdk-facade-validation/{producer['tree']}/{target}"):
                _require_capability_output_separate(output, [archive])
        ready_bytes, producer_bytes = canonical_json_bytes(ready), canonical_json_bytes(producer)
        if _read(inputs / "phase-plan.json") != ready_bytes:
            raise ValueError("Core retained election differs from its selected plan")
        for field, receipt_field, name in (
            (value["packageStage"], value["packageReceipt"], "sdk-sdk-core-package-common"),
            (value["validationContractEvidence"]["stageRoot"], value["validationContractEvidence"]["phaseReceipt"],
             "contract-contract-metadata-common"),
        ):
            selected = inputs / name
            if (_read(selected / "phase-receipt.json") != _read(receipt_field)
                    or _inventory(selected / "stage") != _inventory(Path(field))):
                raise ValueError("Core caller input differs from its elected original predecessor")
        retained[inputs] = _inventory(inputs, allow_empty=True)
        selection = destination / "selection"
        selection.mkdir()
        for name, raw in (("impact-plan.json", before_files["plan"]), ("phase-plan.json", ready_bytes),
                          ("producer.json", producer_bytes)):
            (selection / name).write_bytes(raw)
        retained[selection] = _inventory(selection)
        invocation = _retain_request(request, value, destination / "originals")
        retained[destination / "originals"] = _inventory(destination / "originals", allow_empty=True)
        original_context = {"repositoryRoot": str(root), "androidSdkDirectory": android_sdk_directory}
        if consumer_java_executable is not None:
            original_context["javaExecutable"] = str(Path(consumer_java_executable).absolute())
            if os.name != "nt" or str(Path(environ.get("JAVA_HOME", "")) / "bin/java.exe") != original_context["javaExecutable"]:
                raise ValueError("Core Windows consumer Java must equal the selected outer JAVA_HOME launcher")
        _context(original_context, {"producer": producer, "target": target})
        context_bytes = canonical_json_bytes(original_context)
        unchanged()
        result = execute_validation(ready, producer=producer, repository_root=root,
            destination=destination / "worker", facade_request=invocation, environ=environ)
        retained[destination / "worker"] = _inventory(destination / "worker", allow_empty=True)
        work_before = _inventory(result["work"], allow_empty=True)
        snapshot_regular_tree(result["work"], destination / "retained-execution", allow_empty=True)
        retained[destination / "retained-execution"] = work_before
        retained[result["work"]] = work_before
        retained[result["stage"]] = result["outputInventory"]
        context = destination / "context"
        context.mkdir()
        write_canonical_json(context / "execution-context.json", {
            "schemaVersion": 1, "target": target, "buildKey": ready["buildKey"], "producer": producer,
            "originalContext": original_context, "workerDirectory": str(destination / "worker"),
        })
        retained[context] = _inventory(context)
        trust = "development" if producer["event"] == "pull_request" else "release"
        with tempfile.TemporaryDirectory(prefix="core-validation-replay-") as temporary:
            private = Path(temporary).resolve()
            receipt = write_phase_receipt(result["stage"], private, "sdk", "sdk-core", "validation", target,
                value["sdkVersion"], ready["buildKey"], ready["inputs"], producer, trust)
            raw = canonical_json_bytes(receipt)
            verified, verified_bytes = verify_sdk_facade_validation_original_content(
                repository=root, validation_stage=result["stage"], validation_receipt=private / "phase-receipt.json",
                facade_request=invocation, prepared_inputs=result["inputs"], execution_directory=result["execution"],
                consumer_inputs=result["consumerInputs"], compiler_inputs=result["work"] / "compiler-inputs.json",
                original_context=original_context,
                native_compiler_archive=archive,
                tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
                java_executable=java_executable, policy_revision=policy_revision,
                required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory)
            if (verified_bytes != raw or canonical_json_bytes(verified) != raw
                    or _read(private / "phase-receipt.json") != raw):
                raise ValueError("Core full replay returned a different original receipt")
        if (canonical_json_bytes(ready) != ready_bytes or canonical_json_bytes(producer) != producer_bytes
                or canonical_json_bytes(original_context) != context_bytes):
            raise ValueError("Core selected execution policy changed during validation")
        unchanged()
        product_reuse._runtime_worker_checkout(root, producer)
        shard = product_reuse.finalize_phase_object(stage_root=result["stage"], phase_plan=ready,
            producer=producer, product_version=value["sdkVersion"], trust_domain=trust, destination=destination / "shard")
        if shard["receiptBytes"] != raw:
            raise ValueError("Core finalized receipt differs from full original replay")
        return {**result, "shard": shard, "originals": destination / "originals"}
    finally:
        unchanged()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "repository-root", "facade-request",
                 "tooling-evidence", "tooling-public-key", "java-executable"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    parser.add_argument("--target", choices=SDK_FACADE_TARGETS, required=True)
    for name in ("expected-build-key", "policy-revision", "android-sdk-directory"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    for name in ("consumer-java-executable", "tooling-keyring", "tooling-keys-directory", "sdk-apple-validation-policy",
                 "native-compiler-archive"):
        parser.add_argument("--" + name, type=Path)
    arguments = vars(parser.parse_args(argv))
    if (arguments["tooling_keyring"] is None) != (arguments["tooling_keys_directory"] is None):
        parser.error("Core tooling keyring and directory must be supplied together")
    try:
        policy = arguments.pop("sdk_apple_validation_policy")
        if policy is not None:
            arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(
                policy, "Caller Apple validation policy")
        execute(**arguments, environ=os.environ)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
