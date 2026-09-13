"""Verify original SDK package inputs using the existing product planner."""

import argparse
import base64
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import sys
import tempfile
from typing import Any

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
    native_runtime_validation_dependencies, plan_phase,
)
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity, write_output_manifest
from .registry import (
    NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId, phase_instance_dependencies, required_contract_components,
)
from .sdk_compatibility import load_sdk_compatibility_request
from .sdk_inputs import COMPATIBILITY_NAME, REQUEST_NAME, _copy_file, stage_sdk_inputs
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


def _capture_validation_sources(repository: Path, validation: dict[str, Any], stage: Path, output: Path) -> None:
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
    result = plan_phase(
        _instance(receipt), inventory=phase_git_inventory(repository, commit, _instance(receipt)),
        versions=versions, upstream_receipts=upstream,
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
        flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1,
        contract_projection=projection.restrict(required_contract_components(_instance(receipt))),
        native_runtime_projections=native_projections,
    )
    if receipt["inputs"] != result["inputs"] or receipt["buildKey"] != result["buildKey"]:
        raise ValueError("SDK receipt inputs/build key differ from its original authenticated plan")


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
    if apple_verification is not None:
        from .sdk_maven import _APPLE_VERIFICATION_KEYS
        if (instance != PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
                or type(apple_verification) is not dict
                or set(apple_verification) != _APPLE_VERIFICATION_KEYS):
            raise ValueError("Apple package inputs require exact iOS identity and complete caller verification")
        if Path(apple_verification["repository"]).resolve(strict=True) != repository.resolve(strict=True):
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
        if runtime_stage_root is None or staged_sdks is None or any(value is not None for value in (
            binary_stage_root, binary_receipt_path, binary_contract_evidence,
        )):
            raise ValueError("Native SDK input verification requires only its Runtime staging inputs")
    elif binary_stage_root is None or binary_receipt_path is None or binary_contract_evidence is None or \
            runtime_stage_root is not None or staged_sdks is not None:
        raise ValueError("Maven SDK input verification requires its original binary and Contract evidence")

    with tempfile.TemporaryDirectory(prefix="sdk-package-plan-") as temporary:
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
            stage_sdk_inputs(Path(compatibility_request), handoff)
        else:
            captured_request = root / "captured-request.json"
            captured_request.write_bytes(original_request_bytes)
            request_directory = Path(compatibility_request).parent
            original_arguments = load_sdk_compatibility_request(captured_request, request_directory=request_directory)
            from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
            if validation_content_output is not None:
                _require_capability_output_separate(validation_content_output, (
                    Path(stage_root), Path(receipt_path), Path(compatibility_request), runtime_stage_root, staged_sdks,
                    Path(validation_stage_root), Path(validation_receipt_path),
                    _original_artifact_directories(original_arguments),
                    original_arguments["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY,
                ))
            _require_capability_output_separate(validation_inputs_output, (
                Path(stage_root), Path(receipt_path), Path(compatibility_request), runtime_stage_root, staged_sdks,
                Path(validation_receipt_path) if validation_receipt_path is not None else None,
                Path(validation_stage_root) if validation_stage_root is not None else None,
                original_arguments,
                original_arguments["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY,
            ))
            stage_sdk_inputs(captured_request, handoff, request_directory=request_directory)
        arguments = load_sdk_compatibility_request(handoff / REQUEST_NAME)
        if apple_verification is not None and apple_verification["required_trust_domain"] != arguments["required_trust_domain"]:
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
            from .sdk_native import verify_native_sdk_package_phase
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
            )
        else:
            from .sdk_maven import verify_packaged_sdk_maven_phase, verify_sdk_maven_binary_predecessor
            if binary_contract_evidence.get("expectedTrustDomain") != arguments["required_trust_domain"]:
                raise ValueError("SDK binary Contract evidence cannot change the required trust domain")
            apple_options = {"apple_verification": apple_verification} if apple_verification is not None else {}
            verified, verified_bytes = verify_packaged_sdk_maven_phase(
                stage, captured_receipt, handoff / REQUEST_NAME, **apple_options,
            )
            binary, _ = verify_sdk_maven_binary_predecessor(
                binary_stage_root, binary_receipt_path, stage, captured_receipt, handoff / COMPATIBILITY_NAME,
                **apple_options,
            )
            binary_projection = _contract_projection_from_request(_instance(binary), versions, binary_contract_evidence)
            binary_contract, _ = _receipt(Path(binary_contract_evidence["phaseReceipt"]))
            _verify_plan(repository, binary, versions, [binary_contract], binary_projection)
            manifest = verify_contract_bundle(arguments["contract_payload"])
            if any(record["sha256"] != manifest["components"][record["component"]]["sha256"]
                   for record in binary_projection.receipt_value()["componentDigests"]):
                raise ValueError("SDK binary original Contract components differ from package-selected Contract")
            upstream[_instance(binary)] = binary
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
            _stage_native_capability_inputs(arguments, runtime_stage_root, staged_sdks, prepared)
            (prepared / "receipts/sdk-package.json").write_bytes(original)
            if validation_stage_root is not None:
                _capture_validation_sources(repository, validation, validation_stage, prepared)
                snapshot_regular_tree(validation_stage, prepared / "validation")
                (prepared / "receipts/sdk-validation.json").write_bytes(validation_bytes)
                if regular_file_inventory(Path(validation_stage_root)) != validation_inventory:
                    raise ValueError("Native validation stage changed before publication")
            if (regular_file_inventory(runtime_original) != runtime_inventory
                    or regular_file_inventory(sdks_original) != sdks_inventory
                    or read_regular_file_bytes(Path(compatibility_request), max_bytes=_LIMIT, reject_symlink_parents=True) != original_request_bytes
                    or validation is not None and _receipt(validation_receipt_path)[1] != validation_bytes
                    or _receipt(receipt_path)[1] != original
                    or regular_file_inventory(stage_root) != original_inventory):
                raise ValueError("Native capability sources changed before publication")
            publish_regular_tree(prepared, Path(validation_inputs_output))
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    native = commands.add_parser("verify-native", allow_abbrev=False)
    for name in ("repository", "stage", "receipt", "compatibility-request", "runtime-stages", "staged-sdks"):
        native.add_argument(f"--{name}", type=Path, required=True)
    native.add_argument("--component", choices=NATIVE_BINDINGS, required=True)
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
