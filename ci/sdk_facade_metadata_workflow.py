"""Produce elected Core metadata through eleven held original content replays.

No hosted hardware/toolchain or catalog admission is granted here. The fixed
producer joins existing contents; it never rebuilds or re-signs validations.
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, snapshot_regular_tree, write_canonical_json,
)
from products.receipt import validate_producer, verify_output_manifest_identity
from products.registry import PhaseInstanceId, SDK_FACADE_TARGETS
from products.restore import verify_phase_shard
from products.sdk_facade_inputs import _request, _sources
from products.sdk_facade_validation import _inventory
from products.sdk_apple_validation_admission import apple_validation_policy_arguments
from products.sdk_package import _require_capability_output_separate
from products.sdk_platform_metadata import OUTPUT_KIND, OUTPUT_PATH
from products.sdk_validation_inputs import _request_inventory
from products.signing_isolation import require_no_signing_secret
from sdk_facade_metadata_inputs import _records, _native_archives, verified_facade_metadata_inputs


_INSTANCE = PhaseInstanceId("sdk", "sdk-core", "metadata", "common")


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=512 * 1024 * 1024, reject_symlink_parents=True)


def execute(plan, discovery, state, destination, *, expected_build_key, validations,
        contract_digest, component_digests, repository_root, environ, token, trusted_workflow_sha,
        tooling_evidence, tooling_public_key, java_executable, policy_revision, required_trust_domain,
        tooling_keyring=None, tooling_keys_directory=None, sdk_apple_validation_policy=None,
        sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Finalize only after exact election, content comparison and clean reader exit."""
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan = Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(root, discovery, state, destination)
    stage = root / "build/product-stage/sdk/sdk-core/metadata/common"
    records = _records(validations)
    archives = _native_archives(records)
    trees = {discovery, state, Path(tooling_evidence)}
    files = {plan, Path(tooling_public_key), Path(java_executable)}
    compatibility = {}
    for record in records.values():
        request = Path(record["facadeRequest"])
        value, _ = _request(request)
        _, request_trees, request_files = _sources(value)
        trees.update(request_trees.values())
        files.update(request_files.values())
        files.update((request, Path(record["validationReceipt"])))
        compatibility_path = Path(value["compatibilityRequest"])
        compatibility[compatibility_path] = _request_inventory(compatibility_path)
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Core metadata tooling keyring and keys directory must be paired")
    if tooling_keyring is not None:
        files.add(Path(tooling_keyring))
        trees.add(Path(tooling_keys_directory))
    if sdk_apple_validation_policy is not None:
        for path in apple_validation_policy_arguments(sdk_apple_validation_policy).values():
            if isinstance(path, Path):
                (trees if path.is_dir() else files).add(path)
    for output, other in ((destination, stage), (stage, destination)):
        _require_capability_output_separate(output, [other, *trees, *files, *archives,
            *(path for inventory in compatibility.values() for path in inventory)])
        if (root not in output.parents or output.resolve(strict=False) != output
                or output.exists() or output.is_symlink()):
            raise ValueError("Core metadata requires fresh normalized task-owned outputs")
    before_trees = {path: _inventory(path, allow_empty=True) for path in trees}
    before_files = {path: _read(path) for path in files}

    def policy_bytes():
        return canonical_json_bytes({"validations": _records(validations), "contractDigest": contract_digest,
            "componentDigests": component_digests, "applePolicy": sdk_apple_validation_policy})

    policy = policy_bytes()
    retained = {}
    identities = []

    def unchanged():
        require_no_signing_secret(environ)
        if (policy_bytes() != policy
                or _native_archives(records) != archives
                or any(_read(path) != raw for path, raw in before_files.items())
                or any(_inventory(path, allow_empty=True) != before for path, before in before_trees.items())
                or any(_request_inventory(path) != inventory for path, inventory in compatibility.items())
                or any(_inventory(path, allow_empty=True) != before for path, before in retained.items())
                or any(canonical_json_bytes(value) != raw for value, raw in identities)):
            raise ValueError("Core metadata election, originals, caller policy or retained outputs changed")

    tooling = {"evidence": str(Path(tooling_evidence).absolute()), "publicKey": str(Path(tooling_public_key).absolute()),
        "javaExecutable": str(Path(java_executable).absolute()), "requiredTrustDomain": required_trust_domain,
        "keyring": str(Path(tooling_keyring).absolute()) if tooling_keyring is not None else None,
        "keysDirectory": str(Path(tooling_keys_directory).absolute()) if tooling_keys_directory is not None else None}
    optional = {"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}
    optional.update({name: value for name, value in (
        ("sdk_facade_metadata_admission", sdk_facade_metadata_admission),
        ("sdk_android_metadata_admission", sdk_android_metadata_admission)) if value is not None})
    try:
        elected = product_reuse._verified_product_state(plan, discovery, state, root, environ, tooling,
            sdk_original_workflow_sha=trusted_workflow_sha, **optional)
        ready = elected.prior_ready_plans.get(_INSTANCE)
        if ready is None or ready["buildKey"] != expected_build_key:
            raise ValueError("Core metadata is not ready with its exact elected build key")
        producer = validate_producer(elected.producer, "Core metadata elected producer")
        version = elected.expected_fixed["versions"]["sdk"]
        identities.extend((value, canonical_json_bytes(value)) for value in (ready, producer))
        unchanged()
        destination = product_reuse._prepare_destination(destination, root)
        prepared = destination / "inputs"
        materialized = product_reuse.materialize_product_predecessors(plan, discovery, state, _INSTANCE, prepared,
            expected_build_key=expected_build_key, repository_root=root, environ=environ,
            sdk_validation_tooling=tooling, sdk_original_workflow_sha=trusted_workflow_sha, **optional)
        if (materialized != ready or _read(prepared / "phase-plan.json") != canonical_json_bytes(ready)
                or _read(prepared / "producer.json") != canonical_json_bytes(producer)):
            raise ValueError("Core metadata materialized election differs from authenticated state")
        identities.append((materialized, canonical_json_bytes(materialized)))
        retained[prepared] = _inventory(prepared, allow_empty=True)
        for target in SDK_FACADE_TARGETS:
            if _read(prepared / f"sdk-sdk-core-validation-{target}/phase-receipt.json") != _read(records[target]["validationReceipt"]):
                raise ValueError("Core metadata caller validation differs from its elected predecessor")
        selection = destination / "selection"
        selection.mkdir()
        for name, raw in (("impact-plan.json", before_files[plan]), ("phase-plan.json", canonical_json_bytes(ready)),
                          ("producer.json", canonical_json_bytes(producer))):
            (selection / name).write_bytes(raw)
        retained[selection] = _inventory(selection)
        unchanged()
        with verified_facade_metadata_inputs(plan=plan, validations=validations, contract_digest=contract_digest,
                component_digests=component_digests, repository_root=root, environ=environ, token=token,
                trusted_workflow_sha=trusted_workflow_sha, tooling_evidence=tooling_evidence,
                tooling_public_key=tooling_public_key, java_executable=java_executable, policy_revision=policy_revision,
                required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory) as original:
            package = original["package"]
            selected_package = prepared / "sdk-sdk-core-package-common"
            if (package["receipt"]["productVersion"] != version
                    or _read(selected_package / "phase-receipt.json") != package["receiptBytes"]
                    or _inventory(selected_package / "stage") != _inventory(package["stage"])):
                raise ValueError("Core metadata original package differs from its elected predecessor")
            for target, record in original["validations"].items():
                selected = prepared / f"sdk-sdk-core-validation-{target}"
                if (_read(selected / "phase-receipt.json") != record["receiptBytes"]
                        or _inventory(selected / "stage") != _inventory(record["stage"])):
                    raise ValueError("Core metadata original validation differs from its elected predecessor")
            originals = destination / "originals"
            package_inventory = _inventory(package["stage"])
            snapshot_regular_tree(package["stage"], originals / "package/stage")
            if (_inventory(package["stage"]) != package_inventory
                    or _inventory(originals / "package/stage") != package_inventory):
                raise ValueError("Core metadata package changed during retention")
            (originals / "package/phase-receipt.json").write_bytes(package["receiptBytes"])
            for target, record in original["validations"].items():
                parent = originals / "validations" / target
                capture_inventory = _inventory(record["capture"], allow_empty=True)
                stage_inventory = _inventory(record["stage"])
                snapshot_regular_tree(record["capture"], parent / "capture", allow_empty=True)
                snapshot_regular_tree(record["stage"], parent / "stage")
                if (_inventory(record["capture"], allow_empty=True) != capture_inventory
                        or _inventory(parent / "capture", allow_empty=True) != capture_inventory
                        or _inventory(record["stage"]) != stage_inventory
                        or _inventory(parent / "stage") != stage_inventory):
                    raise ValueError("Core metadata validation changed during retention")
                (parent / "phase-receipt.json").write_bytes(record["receiptBytes"])
            (originals / "metadata-request.json").write_bytes(_read(original["request"]))
            retained[originals] = _inventory(originals, allow_empty=True)
            expected = original["expectedContentBytes"]
            if canonical_json_bytes(original["expectedContent"]) != expected:
                raise ValueError("Core metadata expected content changed")
            worker = destination / "worker"
            environment, wrapper = product_reuse._runtime_worker_environment(root, producer, worker, environ)
            product_reuse._prepare_destination(worker, root)
            fields = {"codexAgent.product": "sdk", "codexAgent.component": "sdk-core", "codexAgent.phase": "metadata",
                "codexAgent.target": "common", "codexAgent.sdkVersion": version,
                "codexAgent.candidateCommit": producer["commit"], "codexAgent.candidateTree": producer["tree"],
                "codexAgent.sdkFacadeMetadataRequest": str(original["request"])}
            command = product_reuse._runtime_worker_command(wrapper, fields, environment, build_directory=".")
            unchanged()
            product_reuse._runtime_worker_checkout(root, producer)
            if stage.exists() or stage.is_symlink():
                raise ValueError("Core metadata stage appeared before execution")
            started, code, failure = time.monotonic_ns(), None, None
            try:
                with (worker / "gradle.log").open("xb") as log:
                    result = subprocess.run(command, cwd=root, env=environment, stdout=log,
                        stderr=subprocess.STDOUT, check=False)
                    code = result.returncode
            except OSError as error:
                failure = str(error)
                raise
            finally:
                write_canonical_json(worker / "execution.json", {"schemaVersion": 1, "producer": dict(producer),
                    "buildKey": ready["buildKey"], "command": command, "workingDirectory": str(root),
                    "returnCode": code, "launchError": failure, "elapsedNs": time.monotonic_ns() - started})
                unchanged()
            if code != 0:
                raise ValueError(f"Core metadata phase failed with exit code {code}")
            manifest = verify_output_manifest_identity(stage, "sdk", "sdk-core", "metadata", "common", version)
            if (len(manifest["outputs"]) != 1 or manifest["outputs"][0]["kind"] != OUTPUT_KIND
                    or manifest["outputs"][0]["relativePath"] != OUTPUT_PATH or _read(stage / OUTPUT_PATH) != expected):
                raise ValueError("Core metadata producer differs from exact original content")
            if (worker / "python-bytecode").exists() or (worker / "python-bytecode").is_symlink():
                raise ValueError("Core metadata private bytecode namespace changed")
            retained[stage], retained[worker] = _inventory(stage), _inventory(worker, allow_empty=True)
            upload_before = _inventory(destination, allow_empty=True)
            unchanged()
        unchanged()
        if _read(stage / OUTPUT_PATH) != expected or _inventory(destination, allow_empty=True) != upload_before:
            raise ValueError("Core metadata output changed after original reader exit")
        product_reuse._runtime_worker_checkout(root, producer)
        with tempfile.TemporaryDirectory(prefix="core-metadata-shard-") as temporary:
            candidate = Path(temporary).resolve() / "shard"
            shard = product_reuse.finalize_phase_object(stage_root=stage, phase_plan=ready, producer=producer,
                product_version=version, trust_domain="development" if producer["event"] == "pull_request" else "release",
                destination=candidate)
            unchanged()
            if (verify_phase_shard(candidate, _INSTANCE) != shard
                    or _inventory(destination, allow_empty=True) != upload_before):
                raise ValueError("Core metadata finalized shard changed")
            publish_regular_tree(candidate, destination / "shard")
        return {"stage": stage, "content": stage / OUTPUT_PATH, "outputInventory": retained[stage],
                "diagnostics": worker, "shard": verify_phase_shard(destination / "shard", _INSTANCE)}
    finally:
        unchanged()


def main(argv=None):
    from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options

    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "validations", "component-digests", "repository-root",
                 "tooling-evidence", "tooling-public-key", "java-executable"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    for name in ("expected-build-key", "contract-digest", "trusted-workflow-sha", "policy-revision"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    for name in ("tooling-keyring", "tooling-keys-directory", "sdk-apple-validation-policy"):
        parser.add_argument("--" + name, type=Path)
    add_metadata_admission_arguments(parser)
    arguments = vars(parser.parse_args(argv))
    try:
        require_no_signing_secret(os.environ)
        if (arguments["tooling_keyring"] is None) != (arguments["tooling_keys_directory"] is None):
            raise ValueError("Core metadata tooling keyring and keys directory must be paired")
        for field in ("validations", "component_digests", "sdk_apple_validation_policy"):
            path = arguments[field]
            if path is not None:
                arguments[field] = product_reuse._canonical_control(path, "Caller Core metadata " + field)
        with metadata_admission_options(arguments) as admissions:
            execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""), **admissions)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
