"""Full original Core semantic/Git/key replay, NOT observed-host admission.

The caller must independently authenticate the original worker and its context.
This leaf replays source, signed tooling, package/Contract lineage, imported
repository, generated consumer inputs and process outcomes. It returns only the
unchanged receipt and bytes, never an opaque hosted-execution/admission token.
No catalog or worker-family authority is established here.
"""

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import tempfile
import tomllib

from .inventory import (
    canonical_json_bytes, git_product_versions, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, require_exact_keys, require_string, run_git,
    sha256_bytes, snapshot_regular_tree,
)
from .plan import (
    NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST,
    _contract_projection_from_request, plan_phase,
)
from .receipt import validate_phase_receipt, verify_output_manifest_identity
from .registry import PhaseInstanceId, SDK_FACADE_TARGETS
from .sdk_apple_content import _verify_sdk_apple_with_tooling
from .sdk_facade_inputs import OUTPUT_KIND, OUTPUT_PATH, _request, _sources, prepare_facade_validation_inputs
from .sdk_facade_source import capture_facade_validation_sources
from .sdk_facade_compiler_policy import verify_facade_kotlin_compiler_artifacts
from .sdk_facade_validation import _inventory, _original_path, verify_facade_consumer_evidence
from .sdk_package import _require_capability_output_separate
from .sdk_validation_inputs import _request_inventory
from .selection import phase_git_inventory
from .signing_isolation import require_no_signing_secret


_LIMIT = 16 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _context(value, receipt):
    value = require_exact_keys(value, {"repositoryRoot", "androidSdkDirectory"} |
        ({"javaExecutable"} if type(value) is dict and "javaExecutable" in value else set()),
        "Original facade context")
    original = _original_path(value["repositoryRoot"], "Original facade repository")
    android = value["androidSdkDirectory"]
    if type(android) is not str or "\r" in android or "\n" in android:
        raise ValueError("Original facade Android SDK context is invalid")
    root = PureWindowsPath(original) if PureWindowsPath(original).drive else PurePosixPath(original)
    windows = isinstance(root, PureWindowsPath)
    require_exact_keys(value, {"repositoryRoot", "androidSdkDirectory"} |
        ({"javaExecutable"} if windows else set()), "Original facade platform context")
    launcher = {}
    if windows:
        java = _original_path(value["javaExecutable"], "Original facade Java executable")
        if not PureWindowsPath(java).drive or PureWindowsPath(java).name != "java.exe":
            raise ValueError("Original Windows facade requires its explicit java.exe launcher")
        launcher["javaExecutable"] = java
    work = root / "build/imported-sdk-facade-validation" / receipt["producer"]["tree"] / receipt["target"]
    consumer = work / "consumer"
    return {
        "gradleWrapper": str(root / ("gradlew.bat" if windows else "gradlew")),
        "consumerDirectory": str(consumer), "repositoryDirectory": str(work / "inputs/maven-repository"),
        "outcomeInitScript": str(consumer / ".codex-consumer-task-outcomes.init.gradle.kts"), "environment": {},
        **launcher,
    }, str(work / "execution"), original, android


def verify_sdk_facade_validation_original_content(
    *, repository: Path, validation_stage: Path, validation_receipt: Path,
    facade_request: Path, prepared_inputs: Path, execution_directory: Path,
    consumer_inputs: Path, compiler_inputs: Path, original_context: dict,
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> tuple[dict, bytes]:
    """Replay complete content with explicit original context, not hosted proof.

    facade_request is current caller-owned policy/paths, never a transported
    request selected as authority. original_context has exactly repositoryRoot
    and androidSdkDirectory from the independently authenticated original worker,
    plus javaExecutable for Windows. These paths must bind that original worker's
    immutable source and launcher policy, not the current replay host. Legacy
    Windows bare-gradlew evidence is unsupported and is never relabelled as a
    successful Java-wrapper invocation;
    all nested command paths derive from the committed fixed producer layout.
    Current replay paths are not substituted into original process evidence.
    """
    require_no_signing_secret(os.environ)
    repository = Path(repository).resolve(strict=True)
    request = Path(facade_request)
    value, request_bytes = _request(request)
    if Path(value["repository"]) != repository:
        raise ValueError("Facade caller request belongs to another repository")
    receipt_path = Path(validation_receipt)
    raw = _read(receipt_path)
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if ((receipt["product"], receipt["component"], receipt["phase"]) != ("sdk", "sdk-core", "validation")
            or receipt["target"] not in SDK_FACADE_TARGETS
            or receipt["target"] != value["target"] or receipt["productVersion"] != value["sdkVersion"]):
        raise ValueError("Facade original validation receipt has the wrong identity or version")
    context_bytes = canonical_json_bytes(original_context)
    process_context, execution_path, forbidden_path, android_sdk = _context(original_context, receipt)
    trees = {"stage": Path(validation_stage), "inputs": Path(prepared_inputs),
             "execution": Path(execution_directory), "consumer": Path(consumer_inputs)}
    before = {name: _inventory(path, allow_empty=name != "stage") for name, path in trees.items()}
    _, original_trees, original_files = _sources(value)
    original_files["compilerInputs"] = Path(compiler_inputs)
    tree_before = {name: _inventory(path, allow_empty=True) for name, path in original_trees.items()}
    file_before = {name: _read(path) for name, path in original_files.items()}
    compatibility_before = _request_inventory(Path(value["compatibilityRequest"]))
    package = validate_phase_receipt(load_canonical_json_bytes(file_before["packageReceipt"]))
    contract_raw = file_before["validationContractEvidence/phaseReceipt"]
    contract = validate_phase_receipt(load_canonical_json_bytes(contract_raw))

    def unchanged():
        require_no_signing_secret(os.environ)
        if (_read(receipt_path) != raw or _read(request) != request_bytes
                or canonical_json_bytes(original_context) != context_bytes
                or any(_inventory(path, allow_empty=name != "stage") != before[name] for name, path in trees.items())
                or any(_inventory(path, allow_empty=True) != tree_before[name] for name, path in original_trees.items())
                or any(_read(path) != file_before[name] for name, path in original_files.items())
                or _request_inventory(Path(value["compatibilityRequest"])) != compatibility_before):
            raise ValueError("Original facade inputs, receipt or caller context changed during replay")

    try:
        if receipt["target"] in {"jvm", "android", "node-js", "node-wasm"}:
            verify_facade_kotlin_compiler_artifacts(repository=repository, policy_revision=policy_revision,
                compiler_inputs=original_files["compilerInputs"])
        commit, tree = receipt["producer"]["commit"], receipt["producer"]["tree"]
        try:
            actual_commit = run_git(repository, "rev-parse", f"{commit}^{{commit}}").strip()
            actual_tree = run_git(repository, "rev-parse", f"{commit}^{{tree}}").strip()
        except subprocess.CalledProcessError as error:
            raise ValueError("Original facade source commit is unavailable") from error
        if (actual_commit, actual_tree) != (commit, tree):
            raise ValueError("Original facade source differs from its receipt commit/tree")
        versions = git_product_versions(repository, commit)
        if versions["sdk"] != receipt["productVersion"] or versions["contract"] != value["contractVersion"]:
            raise ValueError("Original facade versions differ from their immutable Git declarations")
        if git_regular_blob_bytes(repository, commit, "gradle/release/sdk-default-runtime.txt", max_bytes=256) != \
                (value["runtimeVersion"] + "\n").encode("ascii"):
            raise ValueError("Original facade Runtime differs from its immutable SDK default")
        instance = PhaseInstanceId("sdk", "sdk-core", "validation", receipt["target"])
        with tempfile.TemporaryDirectory(prefix="facade-original-replay-") as temporary:
            private = Path(temporary).resolve()
            _require_capability_output_separate(private, [repository, request, receipt_path, *trees.values(),
                *original_trees.values(), *original_files.values(), *compatibility_before,
                Path(tooling_evidence), Path(tooling_public_key), Path(java_executable),
                *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)])
            captured = {}
            for name, path in trees.items():
                captured[name] = private / name
                snapshot_regular_tree(path, captured[name], allow_empty=name != "stage")
                if _inventory(captured[name], allow_empty=name != "stage") != before[name]:
                    raise ValueError("Facade original evidence changed during private capture")
            frozen_request = private / "caller-request.json"
            frozen_request.write_bytes(request_bytes)
            regenerated = private / "regenerated-inputs"
            info = prepare_facade_validation_inputs(frozen_request, regenerated)
            if _inventory(regenerated, allow_empty=True) != before["inputs"]:
                raise ValueError("Facade prepared inputs differ from the complete original package/Contract gate")
            for key, stage, expected in (("package", regenerated / "package-stage", package),
                                         ("contract", regenerated / "contract-stage", contract)):
                manifest = verify_output_manifest_identity(stage, expected["product"], expected["component"],
                    expected["phase"], expected["target"], expected["productVersion"])
                if manifest["outputs"] != expected["outputs"]:
                    raise ValueError(f"Facade authenticated {key} stage differs from its original receipt")
            projection = _contract_projection_from_request(instance, versions, value["validationContractEvidence"])
            if (projection is None or projection.receipt_value() != info["contractProjection"]
                    or projection.receipt_value()["receiptSha256"] != sha256_bytes(contract_raw)):
                raise ValueError("Facade selected Contract projection differs from its original receipt")
            planned = plan_phase(instance, inventory=phase_git_inventory(repository, commit, instance),
                versions=versions, upstream_receipts=[package, contract], contract_projection=projection,
                toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
            if (canonical_json_bytes(planned["inputs"]) != canonical_json_bytes(receipt["inputs"])
                    or planned["buildKey"] != receipt["buildKey"]):
                raise ValueError("Original facade validation inputs/build key differ from the authenticated plan")
            source = private / "source"
            source_record = capture_facade_validation_sources(repository, commit, source)
            if source_record["tree"] != tree or _inventory(source) != source_record["files"]:
                raise ValueError("Facade immutable source capture differs from the original receipt")
            kotlin = require_string(tomllib.loads(_read(source / "gradle/libs.versions.toml").decode("utf-8"))
                                    ["versions"]["kotlin"], "Original Kotlin version")
            _verify_sdk_apple_with_tooling(
                sources={"source": (source, False), "consumer": (captured["consumer"], True),
                         "package": (regenerated / "package-stage", False)},
                expected_paths={"compiler-inputs": original_files["compilerInputs"]},
                command_name="verify-original-sdk-facade-consumer-inputs",
                argument_builder=lambda snapshots, expected, work: {
                    "source-snapshot": snapshots["source"], "consumer-inputs": snapshots["consumer"],
                    "compiler-inputs": expected["compiler-inputs"],
                    "package-stage": snapshots["package"], "target": receipt["target"],
                    "contract-version": value["contractVersion"], "runtime-version": value["runtimeVersion"],
                    "sdk-version": value["sdkVersion"], "kotlin-version": kotlin,
                    "original-execution-directory": execution_path, "android-sdk-directory": android_sdk,
                    "forbidden-path": forbidden_path,
                }, repository=repository, tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
                java_executable=java_executable, policy_revision=policy_revision,
                required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory)
            content = verify_facade_consumer_evidence(evidence_directory=captured["execution"], target=receipt["target"],
                sdk_version=value["sdkVersion"], runtime_version=value["runtimeVersion"], contract_version=value["contractVersion"],
                package_stage=regenerated / "package-stage", contract_stage=regenerated / "contract-stage",
                imported_repository=regenerated / "maven-repository",
                expected_package_inventory=info["inventories"]["package"],
                expected_contract_inventory=info["inventories"]["contract"],
                expected_repository_inventory=info["inventories"]["repository"],
                expected_contract_projection=info["contractProjection"], original_context=process_context)
            manifest = verify_output_manifest_identity(captured["stage"], "sdk", "sdk-core", "validation",
                                                       receipt["target"], receipt["productVersion"])
            content_bytes = canonical_json_bytes(content)
            expected_outputs = [{"kind": OUTPUT_KIND, "relativePath": OUTPUT_PATH, "bytes": len(content_bytes),
                                 "sha256": sha256_bytes(content_bytes)}]
            if (manifest["outputs"] != expected_outputs or receipt["outputs"] != expected_outputs
                    or _read(captured["stage"] / OUTPUT_PATH) != content_bytes):
                raise ValueError("Facade original canonical stage/receipt differs from complete replay")
            unchanged()
            if (_read(frozen_request) != request_bytes or _inventory(source) != source_record["files"]
                    or _inventory(regenerated, allow_empty=True) != before["inputs"]
                    or any(_inventory(path, allow_empty=name != "stage") != before[name] for name, path in captured.items())):
                raise ValueError("Facade private inputs changed during original replay")
    finally:
        unchanged()
    return receipt, raw
