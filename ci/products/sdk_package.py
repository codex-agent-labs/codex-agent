"""Verify original SDK package inputs using the existing product planner."""

import argparse
import base64
import importlib.util
from contextlib import ExitStack, contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import sys
import tempfile
from types import FunctionType, SimpleNamespace
from typing import Any
from zipfile import ZipFile

from .contract import verify_contract_bundle
from .contract_projection import verify_contract_component_projection
from .inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_semver, run_git, sha256_bytes, snapshot_regular_tree,
    publish_regular_tree, require_sha256, require_exact_keys, require_integer, require_array,
)
from .plan import (
    NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST,
    _contract_projection_from_request, _native_runtime_projections_from_request,
    native_runtime_validation_dependencies, plan_phase, verified_phase_toolchain_digest,
)
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity, write_output_manifest
from .registry import (
    NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId, phase_instance_dependencies, required_contract_components,
)
from .sdk_compatibility import load_sdk_compatibility_request
from .sdk_inputs import COMPATIBILITY_NAME, INVENTORY_NAME, REQUEST_NAME, _copy_file, stage_sdk_inputs
from .selection import phase_git_inventory


_LIMIT = 16 * 1024 * 1024


def _require_capability_output_separate(output: Path, inputs: Any) -> None:
    destination = Path(output).resolve()
    if isinstance(inputs, dict):
        for value in inputs.values():
            _require_capability_output_separate(output, value)
    elif isinstance(inputs, (tuple, list)):
        for value in inputs:
            _require_capability_output_separate(output, value)
    elif isinstance(inputs, Path):
        source = inputs.resolve()
        if source == destination or source in destination.parents or destination in source.parents:
            raise ValueError("Native capability output overlaps an original input")


def _receipt(path: Path) -> tuple[dict[str, Any], bytes]:
    contents = read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)
    return validate_phase_receipt(load_canonical_json_bytes(contents)), contents


def _original_artifact_directories(inputs: Any) -> list[Path]:
    if isinstance(inputs, dict):
        return [path for value in inputs.values() for path in _original_artifact_directories(value)]
    if isinstance(inputs, (tuple, list)):
        return [path for value in inputs for path in _original_artifact_directories(value)]
    if isinstance(inputs, Path):
        return [inputs if inputs.is_dir() else inputs.parent]
    return []


def _instance(receipt: dict[str, Any]) -> PhaseInstanceId:
    return PhaseInstanceId(*(receipt[key] for key in ("product", "component", "phase", "target")))


def _verify_native_validation_stage(stage: Path, receipt: dict[str, Any], target: str) -> None:
    """Inventory/source-input binding only; the trusted caller must run the full matcher."""
    if (receipt["product"] != "sdk" or receipt["component"] not in NATIVE_BINDINGS
            or receipt["phase"] != "validation" or target not in NATIVE_TARGETS
            or receipt["target"] != target):
        raise ValueError("Native validation stage differs from requested language/host phase")
    manifest = verify_output_manifest_identity(
        stage, "sdk", receipt["component"], "validation", target, receipt["productVersion"],
    )
    if manifest["outputs"] != receipt["outputs"]:
        raise ValueError("Native validation stage differs from original receipt outputs")
    roots = {"native-wrapper-installed": "outputs/installed/",
             "native-wrapper-capability": "outputs/capability/"}
    if receipt["component"] == "cpp":
        roots["native-wrapper-package-negatives"] = "outputs/package-negatives/"
    if {record["kind"] for record in manifest["outputs"]} != set(roots) or any(
        not record["relativePath"].startswith(roots.get(record["kind"], "!"))
        for record in manifest["outputs"]
    ):
        raise ValueError("Native validation stage has unexpected raw evidence kinds/roots")
    if receipt["component"] == "csharp":
        _verify_csharp_restore_execution(stage / "outputs/capability/dotnet-restore-execution.json", target)


def _verify_csharp_restore_execution(path: Path, target: str) -> None:
    """Require the fixed feed-free private restore; raw execution is not host proof."""
    value = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(path,
        max_bytes=_LIMIT, reject_symlink_parents=True)), {
            "schemaVersion", "command", "workingDirectory", "exitCode", "launchError",
            "stdoutBase64", "stderrBase64", "configBase64"}, "C# private restore execution")
    if (type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
            or type(value["exitCode"]) is not int or value["exitCode"] != 0 or value["launchError"] is not None):
        raise ValueError("C# private restore did not complete successfully")
    decoded = {}
    for field in ("stdoutBase64", "stderrBase64", "configBase64"):
        encoded = value[field]
        if type(encoded) is not str:
            raise ValueError("C# restore raw evidence must be canonical Base64")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise ValueError("C# restore raw evidence must be canonical Base64") from error
        if base64.b64encode(raw).decode("ascii") != encoded:
            raise ValueError("C# restore raw evidence must be canonical Base64")
        decoded[field] = raw
    expected_config = (b'<?xml version="1.0" encoding="utf-8"?>\n<configuration><packageSources><clear />'
        b'</packageSources><fallbackPackageFolders><clear /></fallbackPackageFolders></configuration>\n')
    if decoded["configBase64"] != expected_config:
        raise ValueError("C# private restore must use the exact empty-source configuration")
    path_type = PureWindowsPath if target == "windows-x64" else PurePosixPath
    working = value["workingDirectory"]
    command = value["command"]
    if (type(working) is not str or type(command) is not list or not command
            or any(type(part) is not str or not part or any(ord(char) < 32 for char in part) for part in command)):
        raise ValueError("C# private restore command is malformed")
    source, executable = path_type(working), path_type(command[0])
    if (not source.is_absolute() or not executable.is_absolute() or ".." in source.parts
            or ".." in executable.parts or source.name != "source"
            or not source.parent.name.startswith(".csharp-binding-evidence-")
            or str(source) != working):
        raise ValueError("C# restore must execute in its private exact-source snapshot")
    expected = [command[0], "restore", str(source / "tests/CodexAgent.Tests/CodexAgent.Tests.csproj"),
        "--configfile", str(source.parent / "NuGet.Config"), "--packages", str(source.parent / "packages"),
        "--force", "--no-cache", "-p:RestoreSources=", "-p:RestoreAdditionalProjectSources=",
        "-p:RestoreFallbackFolders=", "-p:NuGetAudit=false"]
    if command != expected:
        raise ValueError("C# restore command differs from its fixed offline private recipe")


def _capture_validation_sources(repository: Path, validation: dict[str, Any], stage: Path, output: Path) -> list[dict]:
    # Original validation and package producers may differ. Never read mutable
    # checkout claims or execute an imported producer program.
    component, commit = validation["component"], validation["producer"]["commit"]
    program = {
        "python": "tests/test_enum_parity.py", "csharp": "tests/CodexAgent.Tests/Program.cs",
        "rust": "tests/enum_parity.rs", "cpp": "tests/value_parity_test.cpp",
        "dart": "test/enum_parity_test.dart",
    }[component]
    sources = {"capability-claims.tsv": f"codex-agent-bindings/{component}/parity/capability-claims.tsv",
               "test-program-source": f"codex-agent-bindings/{component}/{program}"}
    if component == "cpp":
        sources["test_installed_package_tamper.py"] = "codex-agent-bindings/cpp/tests/test_installed_package_tamper.py"
    records = []
    for name, path in sources.items():
        contents = git_regular_blob_bytes(repository, commit, path, max_bytes=_LIMIT)
        if not contents:
            raise ValueError("Original validation source evidence is empty")
        # C# transports a compiled DLL, not source-equivalent bytes. Keep its
        # original Program.cs alongside (never in place of) the receipted DLL.
        if name == "test-program-source" and component != "csharp" and contents != \
                read_regular_file_bytes(stage / "outputs/capability/test-program", max_bytes=_LIMIT):
            raise ValueError("Imported capability program differs from original validation Git source")
        destination = output / "validation-source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
        records.append({"relativePath": f"validation-source/{name}",
                        "bytes": len(contents), "sha256": sha256_bytes(contents)})
    return records


def _verify_plan(repository: Path, receipt: dict[str, Any], versions: dict[str, str], upstream: list, projection,
                 native_projections=None) -> None:
    """Replay the sole planner from original Git inputs, never receipt-supplied hashes."""
    commit, tree = receipt["producer"]["commit"], receipt["producer"]["tree"]
    try:
        actual_commit = run_git(repository, "rev-parse", f"{commit}^{{commit}}").strip()
        actual_tree = run_git(repository, "rev-parse", f"{commit}^{{tree}}").strip()
    except subprocess.CalledProcessError as error:
        raise ValueError("SDK receipt original source commit is unavailable") from error
    if actual_commit != commit or actual_tree != tree:
        raise ValueError("SDK receipt original commit/tree differs from repository history")
    version_bytes = git_regular_blob_bytes(repository, commit, "gradle/release/versions/sdk.txt", max_bytes=256)
    if version_bytes != (require_semver(receipt["productVersion"], "SDK product version") + "\n").encode():
        raise ValueError("SDK receipt version differs from its original source version")
    instance = _instance(receipt)
    toolchain_digest = NOT_APPLICABLE_TOOLCHAIN_DIGEST
    if instance.component == "csharp" and instance.phase in {"binary", "package"}:
        from .sdk_dotnet_toolchain import load_sdk_dotnet_profile_bytes
        toolchain_digest = load_sdk_dotnet_profile_bytes(git_regular_blob_bytes(
            repository, commit, "gradle/release/toolchains/sdk/csharp.json", max_bytes=65_536,
        )).digest
        verified_phase_toolchain_digest(repository, commit, instance, toolchain_digest)
    result = plan_phase(
        instance, inventory=phase_git_inventory(repository, commit, instance),
        versions=versions, upstream_receipts=upstream,
        toolchain_profile_digest=toolchain_digest,
        flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1,
        contract_projection=projection.restrict(required_contract_components(instance)),
        native_runtime_projections=native_projections,
    )
    if receipt["inputs"] != result["inputs"] or receipt["buildKey"] != result["buildKey"]:
        raise ValueError("SDK receipt inputs/build key differ from its original authenticated plan")


def csharp_binary_inputs(package_receipt: Path) -> dict[str, Path]:
    """Fixed external input context; its bytes still need full binary/plan checks.

    Validation/metadata callers retain the original binary beside the original
    package receipt. This is an exact transport layout, never artifact discovery
    or an alternative source of trust. Explicit binary arguments remain valid.
    """
    context = Path(package_receipt).parent / "csharp-binary"
    return {"binary_stage_root": context / "stage",
            "binary_receipt_path": context / "phase-receipt.json"}


def verify_sdk_package_inputs(
    repository: Path, stage_root: Path, receipt_path: Path, compatibility_request: Path,
    *, runtime_stage_root: Path | None = None, staged_sdks: Path | None = None,
    binary_stage_root: Path | None = None, binary_receipt_path: Path | None = None,
    binary_contract_evidence: dict[str, Any] | None = None,
    runtime_package_stage: Path | None = None, runtime_package_receipt: Path | None = None,
    validation_inputs_output: Path | None = None,
    validation_receipt_path: Path | None = None,
    validation_stage_root: Path | None = None, validation_target: str | None = None,
    validation_content_output: Path | None = None,
    apple_verification: dict[str, Any] | None = None,
    apple_binary_verification: dict[str, Any] | None = None,
    apple_execution_capture_directory: Path | None = None,
    apple_original_verification: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Verify package semantics, original artifacts and the complete source-input plan.

    This proves content/input binding, not that a claimed CI run actually ran.
    Hosted execution provenance, per-language behavior receipts and protected
    release admission remain separate mandatory checks. No token is minted here.
    Apple verification is supplied by the authenticated caller; it must retain
    the same repository and trust domain, and never relaxes either Maven gate.
    """
    repository = Path(repository)
    stage_root = Path(stage_root)
    receipt, original = _receipt(receipt_path)
    instance = _instance(receipt)
    if sum(value is not None for value in (apple_verification, apple_binary_verification, apple_original_verification)) > 1:
        raise ValueError("Apple package verification modes are mutually exclusive")
    if apple_execution_capture_directory is not None:
        if apple_binary_verification is None:
            raise ValueError("Apple execution capture requires binary package verification")
        _require_capability_output_separate(Path(apple_execution_capture_directory), (
            stage_root, Path(receipt_path), Path(compatibility_request), binary_stage_root,
            binary_receipt_path, *(Path(binary_contract_evidence[name]) for name in (
                "stageRoot", "phaseReceipt", "attestation", "attestationSignature", "publicKey", "keyring", "keysDirectory",
            ) if binary_contract_evidence and binary_contract_evidence.get(name) is not None),
        ))
        original_apple_arguments = load_sdk_compatibility_request(Path(compatibility_request))
        _require_capability_output_separate(Path(apple_execution_capture_directory), original_apple_arguments)
        from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        _require_capability_output_separate(Path(apple_execution_capture_directory),
            original_apple_arguments["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY)
    apple_policy = (apple_original_verification if apple_original_verification is not None else
                    apple_verification if apple_verification is not None else apple_binary_verification)
    if apple_policy is not None:
        from .sdk_maven import _APPLE_VERIFICATION_KEYS, _APPLE_BINARY_VERIFICATION_KEYS, _APPLE_ORIGINAL_VERIFICATION_KEYS
        expected_keys = (_APPLE_ORIGINAL_VERIFICATION_KEYS if apple_original_verification is not None else
                         _APPLE_VERIFICATION_KEYS if apple_verification is not None else _APPLE_BINARY_VERIFICATION_KEYS)
        if (instance != PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
                or type(apple_policy) is not dict
                or set(apple_policy) != expected_keys):
            raise ValueError("Apple package inputs require exact iOS identity and complete caller verification")
        if Path(apple_policy["repository"]).resolve(strict=True) != repository.resolve(strict=True):
            raise ValueError("Apple package verification cannot change the caller repository")
    native = instance.component in NATIVE_BINDINGS
    javascript = instance.component == "javascript"
    validation, validation_bytes = None, None
    if validation_receipt_path is not None:
        validation, validation_bytes = _receipt(validation_receipt_path)
        if (not native or validation["product"] != "sdk" or validation["component"] != instance.component
                or validation["phase"] != "validation" or validation["target"] not in NATIVE_TARGETS):
            raise ValueError("Native SDK validation receipt identity differs from its package")
    if validation_inputs_output is not None and not native:
        raise ValueError("Capability input staging requires a native SDK package")
    if validation_stage_root is not None or validation_target is not None or validation_content_output is not None:
        if (validation_stage_root is None or validation_target is None or validation is None
                or validation_inputs_output is None):
            raise ValueError("Validation stage import requires receipt, expected target and private inputs output")
        _verify_native_validation_stage(Path(validation_stage_root), validation, validation_target)
    if validation_inputs_output is not None:
        original_request_bytes = read_regular_file_bytes(Path(compatibility_request), max_bytes=_LIMIT, reject_symlink_parents=True)
    if instance.product != "sdk" or instance.phase != "package" or (
        not native and not javascript and instance.component not in {"sdk-core", "sdk-android", "sdk-ios"}
    ):
        raise ValueError("SDK input verification requires a supported SDK package phase")
    if javascript:
        if runtime_package_stage is None or runtime_package_receipt is None or any(value is not None for value in (
            runtime_stage_root, staged_sdks, binary_stage_root, binary_receipt_path, binary_contract_evidence,
        )):
            raise ValueError("JavaScript SDK input verification requires only its Node Runtime package")
    elif runtime_package_stage is not None or runtime_package_receipt is not None:
        raise ValueError("Unexpected Node Runtime package inputs for this SDK family")
    elif native:
        csharp_binary = instance.component == "csharp"
        if csharp_binary and binary_stage_root is None and binary_receipt_path is None:
            context = csharp_binary_inputs(receipt_path)
            binary_stage_root, binary_receipt_path = context["binary_stage_root"], context["binary_receipt_path"]
        if (runtime_stage_root is None or staged_sdks is None or binary_contract_evidence is not None
                or (binary_stage_root is None) != (binary_receipt_path is None)
                or (binary_stage_root is not None) != csharp_binary):
            raise ValueError("Native SDK input verification requires its exact Runtime and C# binary inputs")
    elif binary_stage_root is None or binary_receipt_path is None or binary_contract_evidence is None or \
            runtime_stage_root is not None or staged_sdks is not None:
        raise ValueError("Maven SDK input verification requires its original binary and Contract evidence")

    authorization = (Path(receipt_path).parent / "runtime-authorization" / validation_target
                     if validation_stage_root is not None else None)
    for output in (validation_inputs_output, validation_content_output):
        if output is not None:
            _require_capability_output_separate(output, authorization)
    with tempfile.TemporaryDirectory(prefix="sdk-package-plan-") as temporary, ExitStack() as evidence_lifetime:
        root = Path(temporary).resolve()
        if validation_stage_root is not None:
            validation_inventory = regular_file_inventory(Path(validation_stage_root))
            validation_stage = root / "validation"
            snapshot_regular_tree(Path(validation_stage_root), validation_stage)
            if regular_file_inventory(validation_stage) != validation_inventory:
                raise ValueError("Native validation stage changed during snapshot")
            _verify_native_validation_stage(validation_stage, validation, validation_target)
        original_inventory = regular_file_inventory(stage_root)
        stage = root / "package-stage"
        snapshot_regular_tree(stage_root, stage)
        if regular_file_inventory(stage) != original_inventory:
            raise ValueError("SDK package stage changed during input snapshot")
        captured_receipt = root / "package-receipt.json"
        captured_receipt.write_bytes(original)
        handoff = root / "inputs"
        if validation_inputs_output is None:
            handoff_result = stage_sdk_inputs(Path(compatibility_request), handoff)
        else:
            captured_request = root / "captured-request.json"
            captured_request.write_bytes(original_request_bytes)
            request_directory = Path(compatibility_request).parent
            original_arguments = load_sdk_compatibility_request(captured_request, request_directory=request_directory)
            from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
            if validation_content_output is not None:
                _require_capability_output_separate(validation_content_output, (
                    Path(stage_root), Path(receipt_path), Path(compatibility_request), runtime_stage_root, staged_sdks,
                    binary_stage_root, binary_receipt_path,
                    Path(validation_stage_root), Path(validation_receipt_path),
                    _original_artifact_directories(original_arguments),
                    original_arguments["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY,
                ))
            _require_capability_output_separate(validation_inputs_output, (
                Path(stage_root), Path(receipt_path), Path(compatibility_request), runtime_stage_root, staged_sdks,
                binary_stage_root, binary_receipt_path,
                Path(validation_receipt_path) if validation_receipt_path is not None else None,
                Path(validation_stage_root) if validation_stage_root is not None else None,
                original_arguments,
                original_arguments["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY,
            ))
            handoff_result = stage_sdk_inputs(captured_request, handoff, request_directory=request_directory)
        if validation_inputs_output is not None:
            handoff_manifest = canonical_json_bytes(handoff_result["inventory"])
            if (sha256_bytes(handoff_manifest) != handoff_result["inventorySha256"]
                    or read_regular_file_bytes(handoff / INVENTORY_NAME) != handoff_manifest):
                raise ValueError("SDK input handoff differs from verified staging result")
            handoff_inventory = sorted([*handoff_result["inventory"]["files"], {
                "relativePath": INVENTORY_NAME, "bytes": len(handoff_manifest),
                "sha256": sha256_bytes(handoff_manifest),
            }], key=lambda record: record["relativePath"])
            if regular_file_inventory(handoff) != handoff_inventory:
                raise ValueError("SDK input handoff differs from verified staging result")
        arguments = load_sdk_compatibility_request(handoff / REQUEST_NAME)
        if apple_policy is not None and apple_policy["required_trust_domain"] != arguments["required_trust_domain"]:
            raise ValueError("Apple package verification cannot change the authenticated trust domain")
        compatibility = load_canonical_json_bytes((handoff / COMPATIBILITY_NAME).read_bytes())
        aggregate = load_canonical_json_bytes(arguments["runtime_manifest"].read_bytes())
        versions = {
            "sdk": compatibility["sdkVersion"], "contract": compatibility["contract"]["version"],
            "runtime-release": aggregate["runtimeVersion"],
            "runtime-compatibility": aggregate["runtimeCompatibilityVersion"],
        }
        if receipt["productVersion"] != versions["sdk"]:
            raise ValueError("SDK receipt version differs from authenticated selected products")
        contract, contract_bytes = _receipt(arguments["contract_metadata_receipt"])
        upstream = {_instance(contract): contract}
        for path in [arguments["runtime_metadata_receipt"], *(
            path for phases in arguments["variant_phase_receipts"].values() for path in phases.values()
        )]:
            value, _ = _receipt(path)
            upstream[_instance(value)] = value
        # Reconstitute the deterministic metadata stage from the exact original
        # payload/receipt; no producer evidence or reusable payload is rewritten.
        contract_stage = root / "contract-stage"
        _copy_file(arguments["contract_payload"], contract_stage / "outputs" / arguments["contract_payload"].name)
        write_output_manifest(contract_stage, "contract", "contract", "metadata", "common",
                              versions["contract"], {"contract-bundle": "outputs"})
        projection = verify_contract_component_projection(
            contract_stage, contract_bytes, arguments["contract_attestation"],
            arguments["contract_attestation_signature"], arguments["contract_public_key"],
            expected_trust_domain=arguments["required_trust_domain"], expected_contract_version=versions["contract"],
            required_components=required_contract_components(instance),
            keyring=arguments["contract_keyring"], keys_directory=arguments["contract_keys_directory"],
        )
        native_projections = None
        if native:
            native_evidence = [{
                "target": target, "stageRoot": str(runtime_stage_root),
                "phaseReceipts": {phase: str(path) for phase, path in arguments["variant_phase_receipts"][target].items()},
                "payload": str(arguments["variant_bundles"][target]),
                "attestation": str(arguments["variant_attestations"][target]),
                "attestationSignature": str(arguments["variant_attestation_signatures"][target]),
                "publicKey": str(arguments["variant_public_keys"][target]),
                "keyring": str(arguments["runtime_keyring"]) if arguments["runtime_keyring"] else None,
                "keysDirectory": str(arguments["runtime_keys_directory"]) if arguments["runtime_keys_directory"] else None,
            } for target in sorted(NATIVE_TARGETS)]
            native_projections = _native_runtime_projections_from_request(
                instance, list(upstream.values()), native_evidence, projection,
                arguments["contract_payload"], arguments["required_trust_domain"],
            )
        if javascript:
            from .sdk_archive import verify_javascript_sdk_package_phase
            node, node_bytes = _receipt(runtime_package_receipt)
            node_identity = PhaseInstanceId("runtime", "node-js", "package", "node-js")
            attestation = load_canonical_json_bytes(arguments["runtime_attestation"].read_bytes())
            expected = {"component": "node-js", "phase": "package", "target": "node-js",
                        "receiptSha256": sha256_bytes(node_bytes)}
            if _instance(node) != node_identity or expected not in attestation["adapterReceipts"]:
                raise ValueError("SDK Node package receipt differs from authenticated Runtime aggregate")
            node_inventory = regular_file_inventory(runtime_package_stage)
            node_stage, node_receipt = root / "node-stage", root / "node-receipt.json"
            snapshot_regular_tree(runtime_package_stage, node_stage)
            if regular_file_inventory(node_stage) != node_inventory:
                raise ValueError("SDK Node package stage changed during snapshot")
            node_receipt.write_bytes(node_bytes)
            verified, verified_bytes = verify_javascript_sdk_package_phase(
                stage, captured_receipt, handoff / REQUEST_NAME, node_stage, node_receipt,
            )
            upstream[node_identity] = node
        elif native:
            from .sdk_native import SDK_ROOT_PATH, verify_native_sdk_package_phase
            if instance.component == "csharp":
                from .sdk_csharp_binary import verify_csharp_binary_stage
                binary, binary_bytes = _receipt(binary_receipt_path)
                binary_identity = PhaseInstanceId("sdk", "csharp", "binary", "desktop")
                if _instance(binary) != binary_identity:
                    raise ValueError("C# package has the wrong binary predecessor")
                binary_inventory = regular_file_inventory(Path(binary_stage_root))
                binary_stage = root / "csharp-binary-stage"
                snapshot_regular_tree(Path(binary_stage_root), binary_stage)
                if regular_file_inventory(binary_stage) != binary_inventory:
                    raise ValueError("C# binary predecessor changed during snapshot")
                root_key = root / "csharp-sdk-root.pub"
                root_key.write_bytes(git_regular_blob_bytes(repository, receipt["producer"]["commit"],
                                                        SDK_ROOT_PATH, max_bytes=4096))
                verify_csharp_binary_stage(binary_stage, binary, handoff / COMPATIBILITY_NAME, root_key)
                _verify_plan(repository, binary, versions,
                             [upstream[identity] for identity in phase_instance_dependencies(binary_identity)],
                             projection, None)
                upstream[binary_identity] = binary
            if validation_inputs_output is not None:
                runtime_original, sdks_original = Path(runtime_stage_root), Path(staged_sdks)
                runtime_inventory, sdks_inventory = regular_file_inventory(runtime_original), regular_file_inventory(sdks_original)
                runtime_stage_root, staged_sdks = root / "runtime", root / "sdks"
                snapshot_regular_tree(runtime_original, runtime_stage_root)
                snapshot_regular_tree(sdks_original, staged_sdks)
                if (regular_file_inventory(runtime_stage_root) != runtime_inventory
                        or regular_file_inventory(staged_sdks) != sdks_inventory):
                    raise ValueError("Native capability inputs changed during snapshot")
            verified, verified_bytes = verify_native_sdk_package_phase(
                stage, captured_receipt, handoff / REQUEST_NAME, runtime_stage_root, staged_sdks,
                git_regular_blob_bytes(repository, receipt["producer"]["commit"], SDK_ROOT_PATH, max_bytes=4096),
            )
            if authorization is not None:
                # External evidence authenticates the selected default; its signatures
                # never enter the deterministic capability handoff/content projection.
                evidence_lifetime.enter_context(verified_native_consumer_authorization(
                    authorization, staged_sdks, validation_target))
            if instance.component == "csharp":
                archive = stage / "outputs/csharp" / f"CodexAgent.{versions['sdk']}.nupkg"
                with ZipFile(archive) as package:
                    member = package.getinfo("lib/net8.0/CodexAgent.dll")
                    if member.file_size > 64 * 1024 * 1024:
                        raise ValueError("C# package assembly is unreasonably large")
                    with package.open(member) as stream:
                        assembly = stream.read(64 * 1024 * 1024 + 1)
                    if len(assembly) != member.file_size:
                        raise ValueError("C# package assembly length differs from its archive record")
                if (sha256_bytes(assembly) != sha256_bytes(read_regular_file_bytes(
                        binary_stage / "outputs/csharp/CodexAgent.dll", max_bytes=64 * 1024 * 1024))
                        or _receipt(binary_receipt_path)[1] != binary_bytes
                        or regular_file_inventory(Path(binary_stage_root)) != binary_inventory):
                    raise ValueError("C# package assembly differs from its original binary predecessor")
        else:
            from .sdk_maven import verify_packaged_sdk_maven_phase, verify_sdk_maven_binary_predecessor
            if binary_contract_evidence.get("expectedTrustDomain") != arguments["required_trust_domain"]:
                raise ValueError("SDK binary Contract evidence cannot change the required trust domain")
            binary, binary_bytes = _receipt(binary_receipt_path)
            binary_projection = _contract_projection_from_request(_instance(binary), versions, binary_contract_evidence)
            binary_contract, _ = _receipt(Path(binary_contract_evidence["phaseReceipt"]))
            _verify_plan(repository, binary, versions, [binary_contract], binary_projection)
            manifest = verify_contract_bundle(arguments["contract_payload"])
            if any(record["sha256"] != manifest["components"][record["component"]]["sha256"]
                   for record in binary_projection.receipt_value()["componentDigests"]):
                raise ValueError("SDK binary original Contract components differ from package-selected Contract")
            upstream[_instance(binary)] = binary
            apple_options = {"apple_verification": apple_verification} if apple_verification is not None else {}
            if apple_binary_verification is not None or apple_original_verification is not None:
                # Authenticate elected package source identity before executing native parsers.
                _verify_plan(repository, receipt, versions,
                             [upstream[identity] for identity in phase_instance_dependencies(instance)], projection, native_projections)
                captured_binary_receipt = root / "sdk-binary-receipt.json"
                captured_binary_receipt.write_bytes(binary_bytes)
                policy_name = "apple_original_verification" if apple_original_verification is not None else "apple_binary_verification"
                apple_options = {policy_name: apple_policy,
                                 "binary_stage_root": binary_stage_root, "binary_receipt_path": captured_binary_receipt}
                if apple_execution_capture_directory is not None:
                    _require_capability_output_separate(Path(apple_execution_capture_directory),
                                                        _original_artifact_directories(arguments))
                    apple_options["apple_execution_capture_directory"] = Path(apple_execution_capture_directory)
            verified, verified_bytes = verify_packaged_sdk_maven_phase(
                stage, captured_receipt, handoff / REQUEST_NAME, **apple_options,
            )
            if apple_binary_verification is None and apple_original_verification is None:
                verified_binary, verified_binary_bytes = verify_sdk_maven_binary_predecessor(
                    binary_stage_root, binary_receipt_path, stage, captured_receipt, handoff / COMPATIBILITY_NAME,
                    **apple_options,
                )
                if verified_binary != binary or verified_binary_bytes != binary_bytes:
                    raise ValueError("SDK binary receipt changed during semantic verification")
            if _receipt(binary_receipt_path)[1] != binary_bytes:
                raise ValueError("SDK binary receipt changed during semantic verification")
        if verified != receipt or verified_bytes != original:
            raise ValueError("SDK package receipt changed during semantic verification")
        _verify_plan(repository, receipt, versions,
                     [upstream[identity] for identity in phase_instance_dependencies(instance)], projection, native_projections)
        if validation is not None:
            # Verify original validation lineage with the SAME captured/authenticated
            # Contract/Runtime inputs. This alone grants no behavior or host acceptance.
            if validation["productVersion"] != receipt["productVersion"]:
                raise ValueError("Native SDK validation version differs from its package")
            upstream[instance] = receipt
            _verify_plan(repository, validation, versions,
                         [upstream[identity] for identity in phase_instance_dependencies(_instance(validation))],
                         projection, tuple(item for item in native_projections if item.target in {
                             dependency.target for dependency in native_runtime_validation_dependencies(_instance(validation))
                         }))
        if javascript and (_receipt(runtime_package_receipt)[1] != node_bytes or
                           regular_file_inventory(runtime_package_stage) != node_inventory):
            raise ValueError("SDK Node package inputs changed during verification")
        if validation_inputs_output is not None:
            from .sdk_native import _stage_native_capability_inputs
            prepared = root / "capability-inputs"
            expected_files = []

            def include_file(path: str, contents: bytes) -> None:
                expected_files.append({"relativePath": path, "bytes": len(contents),
                                       "sha256": sha256_bytes(contents)})

            def include_tree(prefix: str, records: list[dict]) -> None:
                expected_files.extend({**record, "relativePath": f"{prefix}/{record['relativePath']}"}
                                      for record in records)

            native_validation = runtime_stage_root / "macos-arm64/validation/outputs"
            include_tree("bootstrap", regular_file_inventory(native_validation / "c-abi-bootstrap"))
            include_tree("bootstrap-reference", regular_file_inventory(native_validation / "c-abi-reference"))
            include_tree("sdks", sdks_inventory)
            with ZipFile(arguments["contract_payload"]) as bundle:
                for name in ("canonical-api.json", "canonical-coverage.json"):
                    include_file(f"contract/{name}", bundle.read(f"evidence/{name}"))
                include_file("contract/contract-manifest.json", bundle.read("contract-manifest.json"))
            for name, source in (
                ("runtime-macos-arm64-validation", arguments["variant_phase_receipts"]["macos-arm64"]["validation"]),
                ("runtime-macos-arm64-package", arguments["variant_phase_receipts"]["macos-arm64"]["package"]),
                ("contract-metadata", arguments["contract_metadata_receipt"]),
            ):
                include_file(f"receipts/{name}.json", read_regular_file_bytes(source, max_bytes=_LIMIT))
            _stage_native_capability_inputs(arguments, runtime_stage_root, staged_sdks, prepared)
            (prepared / "receipts/sdk-package.json").write_bytes(original)
            include_file("receipts/sdk-package.json", original)
            if validation_stage_root is not None:
                expected_files.extend(_capture_validation_sources(repository, validation, validation_stage, prepared))
                snapshot_regular_tree(validation_stage, prepared / "validation")
                include_tree("validation", validation_inventory)
                (prepared / "receipts/sdk-validation.json").write_bytes(validation_bytes)
                include_file("receipts/sdk-validation.json", validation_bytes)
                if regular_file_inventory(Path(validation_stage_root)) != validation_inventory:
                    raise ValueError("Native validation stage changed before publication")
            expected_files.sort(key=lambda record: record["relativePath"])
            if regular_file_inventory(prepared) != expected_files:
                raise ValueError("Native capability handoff differs from authenticated source inventory")
            if (regular_file_inventory(runtime_original) != runtime_inventory
                    or regular_file_inventory(runtime_stage_root) != runtime_inventory
                    or regular_file_inventory(sdks_original) != sdks_inventory
                    or regular_file_inventory(staged_sdks) != sdks_inventory
                    or regular_file_inventory(handoff) != handoff_inventory
                    or read_regular_file_bytes(Path(compatibility_request), max_bytes=_LIMIT, reject_symlink_parents=True) != original_request_bytes
                    or validation is not None and _receipt(validation_receipt_path)[1] != validation_bytes
                    or _receipt(receipt_path)[1] != original
                    or regular_file_inventory(stage_root) != original_inventory):
                raise ValueError("Native capability sources changed before publication")
            publish_regular_tree(prepared, Path(validation_inputs_output), expected_inventory=expected_files)
    if _receipt(receipt_path)[1] != original or regular_file_inventory(stage_root) != original_inventory:
        raise ValueError("SDK package stage or receipt changed during input verification")
    if validation is not None and _receipt(validation_receipt_path)[1] != validation_bytes:
        raise ValueError("SDK validation receipt changed during input verification")
    if validation_stage_root is not None and regular_file_inventory(Path(validation_stage_root)) != validation_inventory:
        raise ValueError("SDK validation stage changed during input verification")
    return receipt, original


def native_validation_content(inputs: Path, component: str, target: str) -> dict[str, Any]:
    """Content projection only, NOT authentication or a planner/release capability.

    The trusted Kotlin entry calls this only after original input/source/host,
    full capability and C++ negative verification. Raw receipts remain external.
    """
    if component not in NATIVE_BINDINGS or target not in NATIVE_TARGETS:
        raise ValueError("Unsupported native validation content identity")
    before = regular_file_inventory(inputs)
    package, _ = _receipt(inputs / "receipts/sdk-package.json")
    validation, _ = _receipt(inputs / "receipts/sdk-validation.json")
    if (_instance(package) != PhaseInstanceId("sdk", component, "package", "desktop")
            or _instance(validation) != PhaseInstanceId("sdk", component, "validation", target)
            or package["productVersion"] != validation["productVersion"]):
        raise ValueError("Native validation content differs from original phase identities")
    _verify_native_validation_stage(inputs / "validation", validation, target)
    if component != "csharp" and read_regular_file_bytes(
        inputs / "validation/outputs/capability/test-program", max_bytes=_LIMIT,
    ) != read_regular_file_bytes(inputs / "validation-source/test-program-source", max_bytes=_LIMIT):
        raise ValueError("Native validation source program differs from its captured original")
    contract = load_canonical_json_bytes(read_regular_file_bytes(inputs / "contract/contract-manifest.json", max_bytes=_LIMIT))
    paths = {
        "claims.tsv": "validation-source/capability-claims.tsv",
        "compiler-evidence.tsv": "validation/outputs/capability/compiler-evidence.tsv",
        "executed-tests.tsv": "validation/outputs/capability/executed-tests.tsv",
        "installed.tsv": f"validation/outputs/installed/evidence/{component}/{target}.tsv",
        "test-program-source": "validation-source/test-program-source",
    }
    cases = []
    if component == "cpp":
        paths["package-negative-source.py"] = "validation-source/test_installed_package_tamper.py"
        rows = read_regular_file_bytes(inputs / "validation/outputs/package-negatives/package-tamper-results.tsv",
                                      max_bytes=_LIMIT).decode("utf-8").splitlines()
        if not rows or rows[0] != "caseId\texpectedExit\tactualExitCode\tstatus\tlogPath":
            raise ValueError("Malformed C++ negative content table")
        for row in rows[1:]:
            fields = row.split("\t")
            if (len(fields) != 5 or fields[3] != "passed"
                    or fields[1] != ("zero" if fields[0] == "baseline" else "nonzero")):
                raise ValueError("Unsuccessful C++ negative content case")
            cases.append({"caseId": fields[0], "expectedExit": fields[1], "result": fields[3]})
        expected = sorted(("baseline", "tampered-0", "tampered-1", "tampered-2", "tampered-3",
                           "missing-sidecar", "missing-loader"))
        if [case["caseId"] for case in cases] != expected:
            raise ValueError("Incomplete C++ negative content cases")
    files = []
    for name, path in sorted(paths.items()):
        contents = read_regular_file_bytes(inputs / path, max_bytes=_LIMIT, reject_symlink_parents=True)
        if not contents:
            raise ValueError("Native validation content input is empty")
        files.append({"relativePath": name, "bytes": len(contents), "sha256": sha256_bytes(contents)})
    result = {
        "schemaVersion": 2, "kind": "sdk-native-validation-content", "component": component,
        "target": target, "sdkVersion": package["productVersion"],
        "packageOutputsDigest": output_inventory_digest(package["outputs"]),
        **{key: require_sha256(contract.get(key), f"Native content {key}") for key in
           ("contractDigest", "canonicalApiDigest", "canonicalCoverageDigest")},
        "files": files, "packageNegativeCases": cases,
    }
    if before != regular_file_inventory(inputs):
        raise ValueError("Native validation content inputs changed during projection")
    return result


def native_metadata_content(contents: Path, package_receipt: Path, component: str) -> dict[str, Any]:
    """Join full-gate projections, not receipts or caller-mintable trust tokens.

    Only the trusted Kotlin caller authenticates all original host closures.
    This serializer checks the exact content grammar and common product identity.
    """
    before = regular_file_inventory(contents)
    if {record["relativePath"] for record in before} != {f"{target}.json" for target in NATIVE_TARGETS}:
        raise ValueError("Native metadata requires exactly five target content files")
    package, original = _receipt(package_receipt)
    if component not in NATIVE_BINDINGS or _instance(package) != PhaseInstanceId("sdk", component, "package", "desktop"):
        raise ValueError("Native metadata requires its original language package")
    package_digest = output_inventory_digest(package["outputs"])
    digests = ("contractDigest", "canonicalApiDigest", "canonicalCoverageDigest")
    names = {"claims.tsv", "compiler-evidence.tsv", "executed-tests.tsv", "installed.tsv", "test-program-source"}
    if component == "cpp":
        names.add("package-negative-source.py")
    expected_cases = [{"caseId": case, "expectedExit": "zero" if case == "baseline" else "nonzero", "result": "passed"}
                      for case in sorted(("baseline", "tampered-0", "tampered-1", "tampered-2", "tampered-3",
                                          "missing-sidecar", "missing-loader"))] if component == "cpp" else []
    hosts = []
    for target in sorted(NATIVE_TARGETS):
        value = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
            contents / f"{target}.json", max_bytes=_LIMIT, reject_symlink_parents=True,
        )), {"schemaVersion", "kind", "component", "target", "sdkVersion", *digests,
             "packageOutputsDigest", "files", "packageNegativeCases"},
            "native validation content")
        if (require_integer(value["schemaVersion"], "native content schema", 1) != 2
                or value["kind"] != "sdk-native-validation-content" or value["component"] != component
                or value["target"] != target or value["sdkVersion"] != package["productVersion"]):
            raise ValueError("Native metadata host content has a different product identity")
        if value["packageOutputsDigest"] != package_digest:
            raise ValueError("Native metadata host content belongs to another exact package")
        for key in digests:
            require_sha256(value[key], f"native content {key}")
            if hosts and value[key] != hosts[0][key]:
                raise ValueError("Native metadata hosts have different Contract content")
        files = require_array(value["files"], "native content files")
        for record in files:
            require_exact_keys(record, {"relativePath", "bytes", "sha256"}, "native content file")
            require_integer(record["bytes"], "native content bytes", 1)
            require_sha256(record["sha256"], "native content digest")
        if [record["relativePath"] for record in files] != sorted(names):
            raise ValueError("Native metadata host content has unexpected semantic files")
        if value["packageNegativeCases"] != expected_cases:
            raise ValueError("Native metadata host content lacks exact package negative cases")
        hosts.append(value)
    if before != regular_file_inventory(contents) or _receipt(package_receipt)[1] != original:
        raise ValueError("Native metadata content inputs changed during join")
    return {"schemaVersion": 1, "kind": "sdk-native-metadata-content", "component": component,
            "sdkVersion": package["productVersion"], **{key: hosts[0][key] for key in digests},
            "packageOutputsDigest": package_digest, "hosts": hosts}


@contextmanager
def verified_native_consumer_authorization(evidence: Path, sdks: Path, target: str):
    """Private host-only sidecars; never part of deterministic package/phase bytes."""
    from .c_abi import TARGET_SPECS
    from .sdk_runtime_root import verify_external_library_authorization
    if target not in NATIVE_TARGETS:
        raise ValueError("Native consumer authorization requires an exact host")
    evidence, sdks = Path(evidence), Path(sdks)
    library_path = next(spec.library_path for spec in TARGET_SPECS.values()
                        if spec.classifier == "c-abi-" + target)
    library = sdks / target / library_path
    compatibility_path, root_path = sdks / COMPATIBILITY_NAME, sdks / "sdk-runtime-root.pub"
    compatibility_raw = read_regular_file_bytes(compatibility_path, max_bytes=65536, reject_symlink_parents=True)
    root_raw = read_regular_file_bytes(root_path, max_bytes=4096, reject_symlink_parents=True)
    before = regular_file_inventory(evidence)
    if len(before) > 128 or sum(row["bytes"] for row in before) > _LIMIT:
        raise ValueError("Native consumer authorization exceeds its small evidence bound")
    with tempfile.TemporaryDirectory(prefix="native-consumer-authorization-") as temporary:
        captured = Path(temporary).resolve() / "evidence"
        snapshot_regular_tree(evidence, captured)
        if regular_file_inventory(captured) != before:
            raise ValueError("Native authorization changed during capture")
        transport = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
            captured / "transport.json", max_bytes=_LIMIT, reject_symlink_parents=True)),
            {"schemaVersion", "kind", "target", "source", "observed", "artifact", "files", "rangeBytes", "elapsedNs"},
            "Native authorization transport")
        # Recorded provenance is not authority: the SDK-pinned root below is.
        if (type(transport["schemaVersion"]) is not int or transport["schemaVersion"] != 1
                or transport["kind"] != "sdk-runtime-authorization-capture" or transport["target"] != target
                or transport["files"] != regular_file_inventory(captured / "sidecars")
                or {row["relativePath"].split("/")[0] for row in before} != {"sidecars", "transport.json"}):
            raise ValueError("Native authorization transport differs from captured host sidecars")
        compatibility = load_canonical_json_bytes(compatibility_raw)
        claim = verify_external_library_authorization(captured / "sidecars",
            sdk_pinned_root_public_key=root_raw, sdk_compatibility=compatibility,
            target=target, library_snapshot=library)
        runtime = compatibility["runtime"]
        variant = next(item for item in runtime["embeddedVariants"] if item["target"] == target)
        if (claim["runtimeVersion"] != runtime["defaultRuntimeVersion"]
                or claim["aggregateManifestSha256"] != runtime["defaultManifestSha256"]
                or claim["runtimeIdentity"]["componentId"] != variant["componentId"]
                or any(claim[left] != variant[right] for left, right in (
                    ("runtimeLibrarySha256", "runtimeLibrarySha256"),
                    ("variantBundleSha256", "bundleSha256"), ("variantManifestSha256", "manifestSha256")))):
            raise ValueError("Native consumer authorization differs from the selected SDK Runtime")
        yield captured / "sidecars"
        if (regular_file_inventory(evidence) != before or regular_file_inventory(captured) != before
                or read_regular_file_bytes(compatibility_path, reject_symlink_parents=True) != compatibility_raw
                or read_regular_file_bytes(root_path, reject_symlink_parents=True) != root_raw):
            raise ValueError("Native consumer authorization or SDK policy changed during use")


def consume_authorized_native(repository, packages, sdks, output, sdk_version, language, *,
                              runtime_authorization, expected_classifier, offline=False,
                              package_negative_evidence=None):
    """Reuse the unchanged installed consumer with one additional staging seam.

    A private function namespace keeps the package-producing module and its
    globals untouched. All original path, package, equality and consumer gates
    execute; each installed loader still verifies its own signed sidecars.
    """
    from ci import native_wrappers
    for destination in (output, package_negative_evidence):
        if destination is not None:
            _require_capability_output_separate(destination, Path(runtime_authorization))
    namespace = dict(vars(native_wrappers))

    def bind(name):
        original = getattr(native_wrappers, name)
        bound = FunctionType(original.__code__, namespace, original.__name__,
                             original.__defaults__, original.__closure__)
        bound.__kwdefaults__ = original.__kwdefaults__
        return bound

    original_consumer = bind("_consume")

    def authorized_consumer(*args, **kwargs):
        matches = []

        def matching_native(root, pattern, sdk_library, label):
            native = native_wrappers.require_matching_native(root, pattern, sdk_library, label)
            if matches:
                raise ValueError("Native consumer must select exactly one installed library")
            matches.append(native)
            return native

        with verified_native_consumer_authorization(runtime_authorization, sdks, expected_classifier) as evidence:
            external_calls = []

            def run(*command, **options):
                if language == "csharp" and command[:2] == ("dotnet", "restore"):
                    # .NET 8 names this switch --no-cache; preserve the original
                    # local-only source, isolated package cache and forced restore.
                    command = tuple("--no-cache" if value == "--no-http-cache" else value
                                    for value in command)
                if language == "rust" and "codex-agent-rust-lifecycle-smoke" in command:
                    if (len(matches) != 1 or tuple(command[:-1]) != (
                            "cargo", "run", "--manifest-path", options["cwd"] / "rust-consumer/Cargo.toml",
                            "--release", "--locked", "--offline", "--bin",
                            "codex-agent-rust-lifecycle-smoke", "--")):
                        raise ValueError("Rust fixture consumer invocation differs from the fixed test path")
                    return run_rust_fixture_consumer(matches[0].parents[2],
                        options["cwd"] / "rust-consumer/src/bin/lifecycle_smoke.rs",
                        Path(command[-1]), environ=options["env"])
                if not matches or not any(str(value) == str(matches[0]) for value in command):
                    return native_wrappers.run(*command, **options)
                # Only the explicit external-positive invocation sees sidecars.
                # Package-negative fixtures and deterministic evidence never copy them.
                sidecar = matches[0].with_name(matches[0].name + ".evidence")
                inventory = regular_file_inventory(evidence)
                publish_regular_tree(evidence, sidecar, expected_inventory=inventory)
                try:
                    result = native_wrappers.run(*command, **options)
                    if regular_file_inventory(sidecar) != inventory:
                        raise ValueError("Installed consumer changed its Runtime authorization")
                    external_calls.append(True)
                    return result
                finally:
                    native_wrappers.invalidate_output(sidecar)

            namespace.update(require_matching_native=matching_native, run=run)
            original_consumer(*args, **kwargs)
            if len(matches) != 1 or len(external_calls) != 1:
                raise ValueError("Native consumer must authenticate exactly one external-positive invocation")

    namespace["_consume"] = authorized_consumer
    # Keep the original output guards and exception cleanup around authorization too.
    bind("consume_language")(repository, packages, sdks, output, sdk_version, language,
        expected_classifier=expected_classifier, offline=offline,
        package_negative_evidence=package_negative_evidence)


def run_rust_fixture_consumer(package: Path, program: Path, fixture: Path, *, environ):
    """Compile the existing smoke as a unit test using the shipped cfg(test) seam.

    Public embedded/external consumers run unchanged first. This private source
    overlay tests the unsigned mock; it neither changes nor republishes the crate.
    """
    program_raw = read_regular_file_bytes(program, reject_symlink_parents=True)
    source = program_raw.decode("utf-8")
    replacements = (
        ("use codex_agent::{", "use crate::{"),
        ("fn main() -> Result<(), CodexError> {", "#[test]\nfn main() -> Result<(), CodexError> {"),
        ('std::env::args_os()\n            .nth(1)', 'std::env::var_os("CODEX_AGENT_INSTALLED_TEST_FIXTURE")'),
        ("CodexNativeLibrary::load(&library)?", "CodexNativeLibrary::load_fixture_for_test(&library)?"),
    )
    for old, new in replacements:
        if source.count(old) != 1:
            raise ValueError("Rust fixture consumer source differs from the reviewed test-only overlay")
        source = source.replace(old, new)
    original_sources = regular_file_inventory(package / "src")
    originals = {name: read_regular_file_bytes(package / name, reject_symlink_parents=True) for name in (
        "Cargo.toml", "Cargo.lock", "build.rs", "native/sdk-compatibility.json", "native/sdk-runtime-root.pub")}
    with tempfile.TemporaryDirectory(prefix="rust-installed-fixture-") as temporary:
        root = Path(temporary).resolve()
        snapshot_regular_tree(package / "src", root / "src")
        if regular_file_inventory(root / "src") != original_sources:
            raise ValueError("Installed Rust sources changed during fixture capture")
        for name, raw in originals.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        # No Cargo.toml.orig or native bodies: this is a source unit harness,
        # not another package build or public-loader authentication test.
        unit = root / "src/codex_installed_fixture.rs"
        if unit.exists():
            raise ValueError("Rust fixture overlay collides with an installed source")
        unit.write_text(source, encoding="utf-8", newline="\n")
        library = root / "src/lib.rs"
        library.write_bytes(library.read_bytes() + b"\n#[cfg(test)]\nmod codex_installed_fixture;\n")
        # Reuse the caller's already-built dependencies, never a second cold
        # Cargo target tree. The normal consumer owns and removes this scratch.
        target = Path(environ.get("CARGO_TARGET_DIR", root / "target"))
        if not target.is_absolute():
            raise ValueError("Rust fixture Cargo target must be an explicit private path")
        _require_capability_output_separate(target, [package, program, fixture])
        result = subprocess.run(["cargo", "test", "--manifest-path", str(root / "Cargo.toml"),
            "--lib", "--release", "--locked", "--offline", "codex_installed_fixture::main", "--", "--exact"],
            cwd=root, env={**environ, "CARGO_TARGET_DIR": str(target),
                "CODEX_AGENT_INSTALLED_TEST_FIXTURE": str(fixture)}, capture_output=True, check=False)
        sys.stdout.buffer.write(result.stdout)
        sys.stderr.buffer.write(result.stderr)
        if (result.returncode != 0 or b"test codex_installed_fixture::main ... ok" not in result.stdout
                or b"test result: ok. 1 passed; 0 failed;" not in result.stdout):
            raise ValueError("Rust test-only installed lifecycle did not execute successfully")
        if (regular_file_inventory(package / "src") != original_sources
                or read_regular_file_bytes(program, reject_symlink_parents=True) != program_raw
                or any(read_regular_file_bytes(package / name, reject_symlink_parents=True) != raw
                       for name, raw in originals.items())):
            raise ValueError("Installed Rust fixture inputs changed during execution")


def rust_lifecycle_unit_source(original: bytes) -> bytes:
    """Move the unchanged lifecycle assertions into the crate's existing test seam."""
    source = original.decode("utf-8")
    marker = "fn lifecycle_state_failure_cancellation_identity_and_ownership()"
    if source.count(marker) != 1 or source.count("use codex_agent::{") != 1:
        raise ValueError("Rust lifecycle source differs from the reviewed unit projection")
    real, mock = source.split(marker)
    if (real.count("CodexNativeLibrary::load(") != 1 or mock.count("CodexNativeLibrary::load(") != 15
            or source.count("#[test]") != 3):
        raise ValueError("Rust lifecycle loader/test inventory differs from the reviewed projection")
    # The genuine imported-SDK test must still authenticate through the PUBLIC loader.
    return (real.replace("use codex_agent::{", "use crate::{") + marker + mock.replace(
        "CodexNativeLibrary::load(", "CodexNativeLibrary::load_fixture_for_test(")).encode("utf-8")


def project_dart_capability_fixtures(source: Path) -> None:
    """Private test compilation only, analogous to Rust's cfg(test) fixture loader.

    Only the four locally compiled mock fixtures register here. Genuine Runtime,
    installed consumers and loader-security tests keep the unmodified auth path.
    No test registration code is added to the shipped Dart library.
    """
    for name in ("leaf_service", "conversation", "agent", "host"):
        path = source / f"test/{name}_parity.dart"
        raw = path.read_text(encoding="utf-8")
        if raw.count("Future<String> _buildFixture() async {") != 1 or raw.count("  return output;") != 1:
            raise ValueError("Dart fixture producer differs from the reviewed projection")
        path.write_text("import 'package:codex_agent/src/ffi.dart' show registerCapabilityFixture;\n" +
                        raw.replace("  return output;", "  return registerCapabilityFixture(output);"), encoding="utf-8")
    path = source / "lib/src/ffi.dart"
    raw = path.read_text(encoding="utf-8")
    marker = "}) {\n  final file = File(path);\n  requireAbsoluteRegularFile(file, 'Codex Agent C SDK');"
    if raw.count(marker) != 1 or "registerCapabilityFixture" in raw:
        raise ValueError("Dart runtime loader differs from the reviewed projection")
    raw = raw.replace(marker, """}) {
  final fixture = _capabilityFixtures[path];
  if (fixture != null) {
    if (beforeDynamicOpen != null || runtimeFileSha256(File(path)) != fixture.digest) {
      throw StateError('Private capability fixture changed');
    }
    return fixture;
  }
  final file = File(path);
  requireAbsoluteRegularFile(file, 'Codex Agent C SDK');""")
    raw += """
// Generated solely in the private capability test compilation, never packaged.
final _capabilityFixtures = <String, _AuthenticatedRuntime>{};
String registerCapabilityFixture(String path) {
  final file = File(path);
  requireAbsoluteRegularFile(file, 'Private capability fixture');
  if (!RegExp(r'^codex_agent_dart_(leaf|conversation|agent|host)_[0-9]+\\.(dylib|dll|so)$')
      .hasMatch(file.uri.pathSegments.last) || _capabilityFixtures.containsKey(path)) {
    throw StateError('Unexpected private capability fixture');
  }
  final digest = runtimeFileSha256(file);
  final library = DynamicLibrary.open(path);
  RuntimeCompatibility.load().verifyRuntimeIdentity(
      readRuntimeIdentity(library), currentClassifier(), embedded: false);
  if (runtimeFileSha256(file) != digest) throw StateError('Private capability fixture changed');
  _capabilityFixtures[path] = _AuthenticatedRuntime(library, digest);
  return path;
}
"""
    path.write_text(raw, encoding="utf-8")


def project_csharp_capability_runtime(source: Path) -> dict[str, bytes]:
    """Private interop projection: C fixture and managed projections share one image.

    The caller independently authenticates the real library and signed sidecars.
    This does not test the public loader; unchanged installed consumers do that.
    The separate fixture-root/security runs still execute the original loader.
    """
    projection = "src/CodexAgent/Interop/NativeLibraryLoader.CapabilityProjection.cs"
    path = source / projection
    if path.exists() or path.is_symlink():
        raise ValueError("C# capability projection collides with original sources")
    path.write_text("""using System.Runtime.InteropServices;
namespace CodexAgent.Interop;
// Generated solely for this private capability test compilation, never packaged.
internal static partial class NativeLibraryLoader
{
    internal static void LoadCapabilityProjection(string path)
    {
        lock (Gate)
        {
            if (loadedHandle != 0) throw new InvalidOperationException("Projection already loaded");
            path = ValidateAbsoluteRegularPath(path, "Authenticated capability Runtime");
            var compatibility = ReadCompatibility();
            var expected = compatibility.Variants[RuntimeTarget].RuntimeLibrarySha256;
            if (Digest(File.ReadAllBytes(path)) != expected)
                throw new InvalidDataException("Capability Runtime digest differs");
            var handle = NativeLibrary.Load(path);
            try
            {
                ValidateLoadedLibrary(handle, compatibility, RuntimeTarget, true);
                if (Digest(File.ReadAllBytes(path)) != expected)
                    throw new InvalidDataException("Capability Runtime changed");
                loadedHandle = handle;
            }
            catch { NativeLibrary.Free(handle); throw; }
        }
    }
}
""", encoding="utf-8")
    test = "tests/CodexAgent.Tests/McpValueParity.cs"
    path = source / test
    raw = path.read_text(encoding="utf-8")
    if raw.count("CodexNativeLibrary.Configure(sdkPath);") != 1:
        raise ValueError("C# MCP producer differs from the reviewed projection")
    path.write_text(raw.replace("CodexNativeLibrary.Configure(sdkPath);",
                               "NativeLibraryLoader.LoadCapabilityProjection(sdkPath);"), encoding="utf-8")
    return {name: read_regular_file_bytes(source / name, reject_symlink_parents=True) for name in (projection, test)}


@contextmanager
def capability_sidecars(native_library: Path, evidence: Path):
    """Expose only the authenticated small sidecars for the private test lifetime."""
    from ci.native_wrappers import invalidate_output
    sidecar = native_library.with_name(native_library.name + ".evidence")
    if sidecar.exists() or sidecar.is_symlink():
        raise ValueError("Capability sidecar destination is already occupied")
    inventory = regular_file_inventory(evidence)
    publish_regular_tree(evidence, sidecar, expected_inventory=inventory)
    try:
        yield
        if regular_file_inventory(sidecar) != inventory:
            raise ValueError("Capability authorization changed during execution")
    finally:
        invalidate_output(sidecar)


def project_cpp_capability_linkage(source: Path) -> dict[str, bytes]:
    # Force the mock object into mock-only tests instead of letting the earlier
    # shared Runtime satisfy its symbols before the static archive is extracted.
    name = "tests/CMakeLists.txt"
    path = source / name
    raw = read_regular_file_bytes(path, reject_symlink_parents=True)
    declaration = b"add_library(codex_agent_mock STATIC mock_codex_agent.cpp)"
    if raw.count(declaration) != 1:
        raise ValueError("C++ mock test linkage declaration changed")
    raw = raw.replace(declaration, declaration.replace(b"STATIC", b"OBJECT"))
    path.write_bytes(raw)
    return {name: raw}


def produce_authorized_native_capabilities(repository: Path, *, language: str, canonical_api: Path, c_abi_bootstrap: Path,
        c_sdk_root: Path, native_library: Path, sdk_compatibility: Path, output: Path,
        runtime_authorization: Path, expected_classifier: str,
        dart_executable: str = "dart", package_config: Path | None = None, dotnet: Path | None = None) -> None:
    """Compose the existing raw producer; no package changes or mock signatures."""
    from .c_abi import TARGET_SPECS
    if language not in NATIVE_BINDINGS:
        raise ValueError("Unsupported authorized capability language")
    directory = "tool" if language == "dart" else "tools"
    script = repository / f"codex-agent-bindings/{language}/{directory}/produce_sdk_validation_evidence.py"
    script_raw = read_regular_file_bytes(script, reject_symlink_parents=True)
    spec = importlib.util.spec_from_file_location(f"{language}_capability_producer", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dart_runner = module._resolved_runner(package_config or module.ROOT / ".dart_tool/package_config.json")[1] if language == "dart" else None
    sdks = sdk_compatibility.parent
    library_path = next(spec.library_path for spec in TARGET_SPECS.values()
                        if spec.classifier == "c-abi-" + expected_classifier)
    if (sdk_compatibility.name != COMPATIBILITY_NAME or c_sdk_root != sdks / expected_classifier
            or native_library != c_sdk_root / library_path):
        raise ValueError("Capability inputs differ from the exact SDK host paths")
    _require_capability_output_separate(output, [runtime_authorization, sdks])
    original_run = subprocess.run
    calls = []
    projected_sources = {}

    with verified_native_consumer_authorization(runtime_authorization, sdks, expected_classifier) as evidence, \
            capability_sidecars(native_library, evidence):
        def run(command, **options):
            source = options["cwd"]
            expected = (["cargo", "test", "--locked", "--offline", "--message-format=json", "--", "--include-ignored"]
                if language == "rust" else [dart_executable, f"--packages={source / '.dart_tool/package_config.json'}",
                    str(dart_runner), "--reporter", "expanded", "test"] if language == "dart"
                else [sys.executable, "-m", "unittest", "discover", "-s", str(source / "tests"), "-v"])
            if calls or command != expected:
                raise ValueError("Unexpected capability producer invocation")
            calls.append(True)
            root = source / {"rust": "native/sdk-runtime-root.pub", "python": "src/codex_agent/native/sdk-runtime-root.pub",
                             "dart": "lib/src/native/sdk-runtime-root.pub"}[language]
            if root.exists() or root.is_symlink():
                raise ValueError("Capability trust root collides with original sources")
            root.write_bytes(read_regular_file_bytes(sdks / "sdk-runtime-root.pub", reject_symlink_parents=True))
            if language == "rust":
                unit = source / "tests/lifecycle_unit.rs"
                if unit.exists() or unit.is_symlink():
                    raise ValueError("Rust capability unit projection collides with original sources")
                unit.write_bytes(rust_lifecycle_unit_source((source / "tests/lifecycle.rs").read_bytes()))
                library = source / "src/lib.rs"
                library.write_bytes(library.read_bytes() +
                    b'\n#[cfg(test)]\n#[path = "../tests/lifecycle_unit.rs"]\nmod codex_lifecycle_fixture;\n')
            elif language == "python":
                # The private suite includes repository packaging-control tests.
                options["env"] = {**options["env"], "PYTHONPATH": str(repository)}
            elif language == "dart":
                project_dart_capability_fixtures(source)
                projected_sources.update({name: read_regular_file_bytes(source / name, reject_symlink_parents=True)
                    for name in ("lib/src/ffi.dart", *(f"test/{name}_parity.dart"
                        for name in ("leaf_service", "conversation", "agent", "host")))})
                options["env"] = {**options["env"], "CODEX_AGENT_LIBRARY": str(native_library)}
            # Lifecycle assertions drain a process-global cleanup registry.
            result = original_run(command[:2] + ["--lib", "--test", "enum_parity"] +
                command[2:] + ["--test-threads=1"] if language == "rust" else command, **options)
            # Explicit target selection excludes doctests; retain the existing
            # compile-fail ownership proof using the SAME Cargo target cache/log.
            if language == "rust":
                original_run(command[:2] + ["--doc"] + command[2:] + ["--test-threads=1"], **options)
            verify_projection(source)
            return result

        def verify_projection(source):
            if any(read_regular_file_bytes(source / name, reject_symlink_parents=True) != raw
                   for name, raw in projected_sources.items()):
                raise ValueError("Capability test projection changed during execution")

        def copy_csharp_sources(files, source):
            if calls:
                raise ValueError("C# capability producer repeated source composition")
            module._copy_sources(files, source)
            projected_sources.update(project_csharp_capability_runtime(source))
            calls.append(True)

        def run_csharp(command, **options):
            verify_projection(options["cwd"])
            module._run_logged(command, **options)
            verify_projection(options["cwd"])

        def copy_cpp_sources(source):
            if calls:
                raise ValueError("C++ capability producer repeated source composition")
            module._copy_sources(source)
            projected_sources.update(project_cpp_capability_linkage(source))
            calls.append(True)

        def run_cpp(command, **options):
            verify_projection(options["cwd"])
            result = original_run(command, **options)
            verify_projection(options["cwd"])
            return result

        def retain(log, source, evidence):
            module._retain_cargo_test_executables(log, source, evidence, lifecycle_as_unit=True)

        namespace = {**vars(module), "subprocess": SimpleNamespace(run=run, STDOUT=subprocess.STDOUT,
            CalledProcessError=subprocess.CalledProcessError)}
        if language == "rust":
            namespace["_retain_cargo_test_executables"] = retain
        elif language == "csharp":
            if dotnet is None or not dotnet.is_absolute():
                raise ValueError("C# capability requires an explicit absolute dotnet executable")
            namespace.update(_copy_sources=copy_csharp_sources, _run_logged=run_csharp)
        elif language == "cpp":
            namespace.update(_copy_sources=copy_cpp_sources, subprocess=SimpleNamespace(
                run=run_cpp, STDOUT=subprocess.STDOUT, CalledProcessError=subprocess.CalledProcessError))
        produce = FunctionType(module.produce.__code__, namespace, module.produce.__name__)
        options = ({"dart_executable": dart_executable, "package_config": package_config} if language == "dart"
                   else {"dotnet": dotnet} if language == "csharp"
                   else {"classifier": expected_classifier} if language == "cpp" else {})
        produce(canonical_api=canonical_api, c_abi_bootstrap=c_abi_bootstrap, c_sdk_root=c_sdk_root,
                native_library=native_library, sdk_compatibility=sdk_compatibility, output=output, **options)
        if calls != [True]:
            raise ValueError("Capability producer did not execute its exact suite")
        if read_regular_file_bytes(script, reject_symlink_parents=True) != script_raw:
            raise ValueError("Capability producer changed during execution")
        for name, raw in projected_sources.items():
            retained = output / "test-projection" / name
            retained.parent.mkdir(parents=True, exist_ok=True)
            with retained.open("xb") as stream:
                stream.write(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for language in NATIVE_BINDINGS:
        capability = commands.add_parser(f"{language}-capabilities", allow_abbrev=False)
        for name in ("repository", "canonical-api", "c-abi-bootstrap", "c-sdk-root", "native-library",
                     "sdk-compatibility", "output", "runtime-authorization"):
            capability.add_argument(f"--{name}", type=Path, required=True)
        capability.add_argument("--expected-classifier", choices=NATIVE_TARGETS, required=True)
        if language == "cpp":
            capability.add_argument("--classifier", choices=NATIVE_TARGETS, required=True)
        if language == "dart":
            capability.add_argument("--dart-executable", default="dart")
            capability.add_argument("--package-config", type=Path)
        if language == "csharp":
            capability.add_argument("--dotnet", type=Path, required=True)
    consumer = commands.add_parser("consume-native", allow_abbrev=False)
    for name in ("repository", "packages", "sdks", "output", "sdk-version-file", "runtime-authorization"):
        consumer.add_argument(f"--{name}", type=Path, required=True)
    consumer.add_argument("--language", choices=NATIVE_BINDINGS, required=True)
    consumer.add_argument("--expected-classifier", choices=NATIVE_TARGETS, required=True)
    consumer.add_argument("--offline", action="store_true")
    consumer.add_argument("--package-negative-evidence", type=Path)
    native = commands.add_parser("verify-native", allow_abbrev=False)
    for name in ("repository", "stage", "receipt", "compatibility-request", "runtime-stages", "staged-sdks"):
        native.add_argument(f"--{name}", type=Path, required=True)
    native.add_argument("--component", choices=NATIVE_BINDINGS, required=True)
    native.add_argument("--binary-stage", type=Path)
    native.add_argument("--binary-receipt", type=Path)
    native.add_argument("--validation-inputs-output", type=Path)
    native.add_argument("--validation-receipt", type=Path)
    native.add_argument("--validation-stage", type=Path)
    native.add_argument("--validation-target", choices=NATIVE_TARGETS)
    native.add_argument("--validation-content-output", type=Path)
    content = commands.add_parser("native-content", allow_abbrev=False)
    content.add_argument("--inputs", type=Path, required=True)
    content.add_argument("--component", choices=NATIVE_BINDINGS, required=True)
    content.add_argument("--target", choices=NATIVE_TARGETS, required=True)
    metadata = commands.add_parser("native-metadata", allow_abbrev=False)
    metadata.add_argument("--contents", type=Path, required=True)
    metadata.add_argument("--package-receipt", type=Path, required=True)
    metadata.add_argument("--component", choices=NATIVE_BINDINGS, required=True)
    args = parser.parse_args(argv)
    if args.command in {f"{language}-capabilities" for language in NATIVE_BINDINGS}:
        if args.command == "cpp-capabilities" and args.classifier != args.expected_classifier:
            raise ValueError("C++ capability classifier differs from authenticated host")
        options = ({"dart_executable": args.dart_executable, "package_config": args.package_config} if args.command == "dart-capabilities"
                   else {"dotnet": args.dotnet} if args.command == "csharp-capabilities" else {})
        produce_authorized_native_capabilities(args.repository, language=args.command.removesuffix("-capabilities"), canonical_api=args.canonical_api,
            c_abi_bootstrap=args.c_abi_bootstrap, c_sdk_root=args.c_sdk_root, native_library=args.native_library,
            sdk_compatibility=args.sdk_compatibility, output=args.output,
            runtime_authorization=args.runtime_authorization, expected_classifier=args.expected_classifier, **options)
        return 0
    if args.command == "consume-native":
        from ci.native_wrappers import require_sdk_version_file
        consume_authorized_native(args.repository.resolve(), args.packages.resolve(), args.sdks,
            args.output.absolute(), require_sdk_version_file(args.sdk_version_file.resolve()), args.language,
            runtime_authorization=args.runtime_authorization, expected_classifier=args.expected_classifier,
            offline=args.offline, package_negative_evidence=args.package_negative_evidence)
        return 0
    if args.command == "native-metadata":
        sys.stdout.buffer.write(canonical_json_bytes(native_metadata_content(args.contents, args.package_receipt, args.component)))
        return 0
    if args.command == "native-content":
        sys.stdout.buffer.write(canonical_json_bytes(native_validation_content(args.inputs, args.component, args.target)))
        return 0
    expected = PhaseInstanceId("sdk", args.component, "package", "desktop")
    original, _ = _receipt(args.receipt)
    if _instance(original) != expected:
        raise ValueError("Native SDK package receipt differs from the requested component")
    verified, _ = verify_sdk_package_inputs(
        args.repository, args.stage, args.receipt, args.compatibility_request,
        runtime_stage_root=args.runtime_stages, staged_sdks=args.staged_sdks,
        binary_stage_root=args.binary_stage, binary_receipt_path=args.binary_receipt,
        validation_inputs_output=args.validation_inputs_output,
        validation_receipt_path=args.validation_receipt,
        validation_stage_root=args.validation_stage, validation_target=args.validation_target,
        validation_content_output=args.validation_content_output,
    )
    if verified != original:
        raise ValueError("Native SDK package receipt changed during CLI verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
