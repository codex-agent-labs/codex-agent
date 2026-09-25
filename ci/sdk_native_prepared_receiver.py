"""Admit one original native preparation upload for the late parallel SDK jobs."""

from __future__ import annotations

import argparse
import fnmatch
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_workflow
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.inventory import (
    canonical_json_bytes, git_file_inventory, git_regular_blob_bytes,
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    sha256_bytes, snapshot_regular_tree, tree_entries,
)
from products.receipt import verify_output_manifest_identity
from products.c_abi import C_ABI_PACKAGE_MANIFEST
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS
from products.sdk_inputs import REQUEST_NAME
from products.sdk_native import (
    SDK_ROOT_PATH, _stage_native_capability_inputs, verify_staged_native_sdk_inputs,
)
from products.sdk_package import _require_capability_output_separate
from products.sdk_compatibility import load_sdk_compatibility_request
from sdk_native_prepare import validate_anchor


_SOURCE_EXCLUDES = {
    "python": ("build/**", "dist/**", "**/__pycache__/**", "**/*.egg-info/**",
               "src/codex_agent/native/sdk-compatibility.json"),
    "csharp": ("artifacts/**", "**/bin/**", "**/obj/**",
               "native/sdk-compatibility.json"),
    "rust": ("target/**", "consumer/target/**", "native/sdk-compatibility.json"),
    "cpp": ("build*/**", "consumer/build*/**"),
    "dart": ("build/**", ".dart_tool/**", ".pub/**", "doc/**",
             "lib/src/native/sdk-compatibility.json"),
}


def _verify_prepared_sources(source, sdks, index, root, commit):
    """Re-derive Gradle's Sync inputs from immutable Git blobs and verified SDKs."""
    source, sdks = Path(source), Path(sdks)
    prefix = "codex-agent-bindings/"
    tracked = []
    for path, _ in tree_entries(root, commit):
        if not path.startswith(prefix):
            continue
        language, _, relative = path[len(prefix):].partition("/")
        if (language in NATIVE_BINDINGS and relative and not any(
                fnmatch.fnmatchcase(relative, pattern) for pattern in _SOURCE_EXCLUDES[language])):
            tracked.append(path)
    expected = {}

    def add(path, file):
        if path in expected:
            raise ValueError(f"Prepared SDK source has overlapping inputs: {path}")
        data = read_regular_file_bytes(file, reject_symlink_parents=True)
        expected[path] = {"relativePath": path, "bytes": len(data), "sha256": sha256_bytes(data)}

    for record in git_file_inventory(root, commit, tracked):
        relative = record["relativePath"].removeprefix(prefix)
        if relative in expected:
            raise ValueError(f"Prepared SDK source has overlapping Git input: {relative}")
        expected[relative] = {**record, "relativePath": relative}
    for record in index["targets"]:
        classifier = record["classifier"]
        native = sdks / classifier
        library = native / record["libraryPath"]
        package_classifier = {"macos-arm64": "osx-arm64", "macos-x64": "osx-x64",
                              "windows-x64": "win-x64"}.get(classifier, classifier)
        for language, directory in (
                ("python", f"src/codex_agent/native/{classifier}"),
                ("csharp", f"native/{package_classifier}"),
                ("rust", f"native/{package_classifier}"),
                ("dart", f"lib/src/native/{classifier}")):
            add(f"{language}/{directory}/{library.name}", library)
        for entry in regular_file_inventory(native):
            if entry["relativePath"] not in {C_ABI_PACKAGE_MANIFEST,
                                              "codex-agent-c-abi-evidence.json"}:
                add(f"cpp/native/{classifier}/{entry['relativePath']}", native / entry["relativePath"])
        for name, input_name in (("sdk-compatibility.json", "sdk-compatibility.json"),
                                 ("sdk-runtime-root.pub", "sdk-runtime-root.pub")):
            add(f"cpp/native/{classifier}/share/CodexAgent/native/{name}", sdks / input_name)
    for language, directory in (
            ("python", "src/codex_agent/native"), ("csharp", "native"),
            ("rust", "native"), ("dart", "lib/src/native")):
        for name in ("sdk-compatibility.json", "sdk-runtime-root.pub"):
            add(f"{language}/{directory}/{name}", sdks / name)
    actual = regular_file_inventory(source)
    if actual != [expected[name] for name in sorted(expected)]:
        raise ValueError("Prepared SDK sources differ from producer Git and verified SDK assets")


def receive(plan, discovery, state, preparation_state, destination, *,
        preparation_component, preparation_phase, preparation_target,
        preparation_build_key, prepared_artifact_id,
        prepared_artifact_sha256, sdk_inputs_artifact_id, sdk_inputs_artifact_sha256,
        trusted_workflow_sha, keyring, keys_directory, repository_root, environ, token,
        sdk_validation_tooling=None, sdk_apple_validation_policy=None,
        sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Export five verified SDKs only after original inputs and contexts exit.

    The output is an external workflow handoff, not a reusable product phase or
    release admission. Prepared source authority remains the exact observed,
    pinned producer job; SDK content is independently recomputed here.
    """
    if preparation_component not in NATIVE_BINDINGS:
        raise ValueError("Native preparation receiver requires one elected language")
    root = Path(repository_root).resolve(strict=True)
    plan = Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    _, preparation_state, _ = product_reuse._product_materialization_paths(
        root, discovery, preparation_state, destination)
    _require_capability_output_separate(destination, [
        plan, discovery, state, preparation_state, Path(keyring), Path(keys_directory),
    ])
    destination.relative_to(root)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Native preparation receiver requires a fresh destination")
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024,
                                         reject_symlink_parents=True)
    controls = {path: regular_file_inventory(path, allow_empty=True)
                for path in {discovery, state, preparation_state}}

    def unchanged():
        if (read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024,
                                    reject_symlink_parents=True) != plan_bytes
                or any(regular_file_inventory(path, allow_empty=True) != files
                       for path, files in controls.items())):
            raise ValueError("Native preparation original plan or state changed")

    tooling = {}
    for name, value in (("sdk_validation_tooling", sdk_validation_tooling),
                        ("sdk_apple_validation_policy", sdk_apple_validation_policy),
                        ("sdk_facade_metadata_admission", sdk_facade_metadata_admission),
                        ("sdk_android_metadata_admission", sdk_android_metadata_admission)):
        if value is not None:
            tooling[name] = value
    with tempfile.TemporaryDirectory(prefix="sdk-native-receiver-", dir=root / "build") as temporary:
        private = Path(temporary).resolve()
        capture, predecessors, runtime = (private / name for name in
                                          ("prepared-upload", "predecessors", "runtime-stages"))
        upload = private / "upload"
        with sdk_workflow.verified_inputs(plan, discovery, state,
                artifact_id=sdk_inputs_artifact_id,
                artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
                keys_directory=keys_directory, repository_root=root,
                environ=environ, token=token, **tooling) as inputs:
            unchanged()
            identity = PhaseInstanceId("sdk", preparation_component,
                                      preparation_phase, preparation_target)
            if {"product": "sdk", "component": preparation_component,
                    "phase": preparation_phase, "target": preparation_target} not in inputs["selection"]["consumers"]:
                raise ValueError("Native preparation anchor is not selected")
            inspected = product_reuse.inspect_products(plan, discovery, preparation_state,
                repository_root=root, environ=environ,
                sdk_original_workflow_sha=trusted_workflow_sha, **tooling)
            elected = [row for row in inspected["readyPlans"] if
                       tuple(row.get(name) for name in ("product", "component", "phase", "target")) ==
                       (identity.product, identity.component, identity.phase, identity.target)]
            if (len(elected) != 1 or set(elected[0]) != PHASE_PLAN_KEYS
                    or elected[0]["buildKey"] != preparation_build_key):
                raise ValueError("Native preparation anchor differs from the elected original")
            anchor = elected[0]
            if validate_anchor(anchor) != identity:
                raise ValueError("Native preparation anchor identity changed")
            anchor_bytes = canonical_json_bytes(anchor)
            transport = product_reuse.capture_sdk_native_prepared_upload(plan, capture,
                expected_phase_plan=anchor, artifact_id=prepared_artifact_id,
                artifact_sha256=prepared_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, repository_root=root,
                environ=environ, token=token)
            capture_files = regular_file_inventory(capture, allow_empty=True)
            product_reuse.materialize_product_predecessors(plan, discovery, state,
                identity, predecessors, expected_build_key=preparation_build_key,
                repository_root=root, environ=environ,
                sdk_original_workflow_sha=trusted_workflow_sha, **tooling)
            predecessor_files = regular_file_inventory(predecessors, allow_empty=True)
            producer = product_reuse.validate_producer(product_reuse._canonical_control(
                predecessors / "producer.json", "Native preparation producer"))
            if transport["captureProducer"] != producer:
                raise ValueError("Native preparation upload differs from elected producer")
            contract = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
                predecessors / "contract-contract-metadata-common/phase-receipt.json",
                "Current Contract metadata"))
            bundles = [row for row in contract["outputs"] if row["kind"] == "contract-bundle"]
            if (tuple(contract[name] for name in ("product", "component", "phase", "target")) !=
                    ("contract", "contract", "metadata", "common") or len(bundles) != 1
                    or bundles[0]["sha256"] != inputs["selection"]["contractPayloadSha256"]):
                raise ValueError("Current Contract differs from authenticated SDK inputs")
            for target in NATIVE_TARGETS:
                for phase in ("package", "validation"):
                    original_id = PhaseInstanceId("runtime", target, phase, target)
                    original = inputs["runtime"]["originalPhases"][original_id]
                    elected_stage = predecessors / f"runtime-{target}-{phase}-{target}"
                    elected_bytes = read_regular_file_bytes(
                        elected_stage / "phase-receipt.json", reject_symlink_parents=True)
                    if elected_bytes != inputs["runtime"]["receiptBytes"][original_id]:
                        raise ValueError("Native preparation Runtime predecessor differs from SDK original")
                    receipt_bytes = read_regular_file_bytes(original["receiptPath"],
                        reject_symlink_parents=True)
                    receipt = original["receipt"]
                    if (receipt_bytes != inputs["runtime"]["receiptBytes"][original_id]
                            or tuple(receipt[name] for name in
                                     ("product", "component", "phase", "target")) !=
                            ("runtime", target, phase, target)):
                        raise ValueError("Native Runtime phase differs from its original receipt")
                    manifest = verify_output_manifest_identity(original["stage"],
                        "runtime", target, phase, target, receipt["productVersion"])
                    if manifest["outputs"] != receipt["outputs"]:
                        raise ValueError("Native Runtime stage differs from its original receipt")
                    elected_manifest = verify_output_manifest_identity(elected_stage / "stage",
                        "runtime", target, phase, target, receipt["productVersion"])
                    if (elected_manifest["outputs"] != receipt["outputs"]
                            or regular_file_inventory(elected_stage / "stage") !=
                            regular_file_inventory(original["stage"])):
                        raise ValueError("Native preparation Runtime stage differs from SDK original")
                    snapshot_regular_tree(original["stage"], runtime / target / phase)
            runtime_files = regular_file_inventory(runtime)
            request = inputs["sdk"]["directory"] / REQUEST_NAME
            sdks = capture / "original/staged-sdks"
            source = capture / "original/prepared-sources"
            root_key = git_regular_blob_bytes(root, producer["commit"], SDK_ROOT_PATH, max_bytes=4096)
            index = verify_staged_native_sdk_inputs(sdks, request, runtime, root_key)
            if (index["sdkVersion"] != inputs["selection"]["sdkVersion"]
                    or index["producerCommit"] != producer["commit"]
                    or index["producerTree"] != producer["tree"]):
                raise ValueError("Native prepared SDK identity differs from its original producer")
            _verify_prepared_sources(source, sdks, index, root, producer["commit"])
            capability = private / "capability"
            _stage_native_capability_inputs(
                load_sdk_compatibility_request(request, request_directory=request.parent),
                runtime, sdks, capability)
            staged = upload / "codex-agent-sdk/build"
            snapshot_regular_tree(sdks, staged / "native-wrapper-c-abi-sdks" / producer["tree"])
            snapshot_regular_tree(source, staged / "native-wrapper-package-sources")
            evidence = upload / "build/ci"
            (evidence / "sdk-contract-evidence").mkdir(parents=True)
            (evidence / "sdk-runtime-evidence").mkdir(parents=True)
            (evidence / "sdk-contract-evidence/canonical-api.json").write_bytes(
                read_regular_file_bytes(capability / "contract/canonical-api.json"))
            (evidence / "sdk-contract-evidence/canonical-coverage.json").write_bytes(
                read_regular_file_bytes(capability / "contract/canonical-coverage.json"))
            (evidence / "sdk-runtime-evidence/bootstrap-evidence.json").write_bytes(
                read_regular_file_bytes(capability / "bootstrap/bootstrap-evidence.json"))
            upload_files = regular_file_inventory(upload)
            if (regular_file_inventory(capture, allow_empty=True) != capture_files
                    or regular_file_inventory(predecessors, allow_empty=True) != predecessor_files
                    or regular_file_inventory(runtime) != runtime_files
                    or canonical_json_bytes(anchor) != anchor_bytes):
                raise ValueError("Native preparation original changed during content verification")
            unchanged()
        unchanged()
        if (regular_file_inventory(capture, allow_empty=True) != capture_files
                or regular_file_inventory(upload) != upload_files):
            raise ValueError("Native preparation output changed after original context exit")
        destination.mkdir(parents=True)
        publish_regular_tree(upload, destination / "upload", expected_inventory=upload_files)
        publish_regular_tree(capture, destination / "prepared-upload", allow_empty=True,
                             expected_inventory=capture_files)
    return {"sdkVersion": index["sdkVersion"], "producer": producer,
            "uploadInventory": upload_files}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "preparation-state-root",
                 "destination", "keyring", "keys-directory", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--preparation-component", choices=NATIVE_BINDINGS, required=True)
    parser.add_argument("--preparation-phase", choices=("package", "validation", "metadata"), required=True)
    parser.add_argument("--preparation-target", required=True)
    for name in ("preparation-build-key", "prepared-artifact-sha256",
                 "sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
        parser.add_argument(f"--{name}", required=True)
    for name in ("prepared-artifact-id", "sdk-inputs-artifact-id"):
        parser.add_argument(f"--{name}", type=int, required=True)
    parser.add_argument("--sdk-validation-tooling", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    args = parser.parse_args(argv)
    arguments = {name.replace("_root", "") if name in {"discovery_root", "state_root"} else name: value
                 for name, value in vars(args).items()
                 if name not in {"sdk_facade_metadata_policy", "sdk_android_metadata_policy"}}
    arguments["preparation_state"] = arguments.pop("preparation_state_root")
    for name in ("sdk_validation_tooling", "sdk_apple_validation_policy"):
        path = arguments.pop(name)
        if path is not None:
            arguments[name] = product_reuse._canonical_control(path, f"Caller {name} policy")
    with metadata_admission_options(args) as admissions:
        receive(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""),
                **admissions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
