"""Execute JS SDK phases inside the caller's verified original-input lifetime.

Returned outputs are not admitted evidence. The caller must successfully exit
its input verification contexts, recheck outputInventory, then finalize the phase.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any

from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_semver, require_sha256, write_canonical_json,
)
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.restore import PHASE_PLAN_KEYS
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from sdk_phase import properties, route


_LIMIT = 16 * 1024 * 1024


def _package(*, root, destination, stage, fields, producer, version, environment,
             tooling, java, build_key, unchanged):
    """Call the same JS producer as Gradle, under the authenticated JAR lifetime."""
    from products.inventory import git_regular_blob_bytes
    from products.receipt import write_output_manifest
    from products.sdk_archive import verify_npm_sdk_compatibility
    from products.sdk_compatibility import load_sdk_compatibility_request, produce_sdk_compatibility
    from products.tooling import verified_tooling_capture

    policy = root / "gradle/release/toolchains/sdk/javascript.json"
    policy_bytes = read_regular_file_bytes(policy, max_bytes=65536, reject_symlink_parents=True)
    if policy_bytes != git_regular_blob_bytes(root, producer["commit"], policy.relative_to(root).as_posix(), max_bytes=65536):
        raise ValueError("JavaScript codec policy differs from the elected producer source")
    java_bytes = read_regular_file_bytes(java, max_bytes=_LIMIT, reject_symlink_parents=True)
    command, return_code, launch_error = [], None, None
    working_directory = None
    started = time.monotonic_ns()
    try:
        with tempfile.TemporaryDirectory(prefix="sdk-javascript-package-") as temporary:
            private = Path(temporary).resolve()
            working_directory = str(private)
            sources = private / "sources"
            sources.mkdir()
            for name in ("package.json.template", "index.cjs", "index.mjs", "index.d.ts", "README.md"):
                (sources / name).write_bytes(git_regular_blob_bytes(root, producer["commit"],
                    "codex-agent-bindings/javascript/package/" + name, max_bytes=_LIMIT))
            for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                (private / name).write_bytes(git_regular_blob_bytes(root, producer["commit"], name, max_bytes=_LIMIT))
            private_inputs = {row["relativePath"]: row for row in _inventory(private)}
            compatibility = stage / "outputs/evidence/sdk-compatibility.json"
            compatibility.parent.mkdir(parents=True)
            arguments = load_sdk_compatibility_request(Path(fields["codexAgent.sdkCompatibilityRequest"]))
            if arguments["sdk_version"] != version:
                raise ValueError("JavaScript compatibility request has a different SDK version")
            produce_sdk_compatibility(**arguments, output=compatibility)
            compatibility_bytes = read_regular_file_bytes(compatibility, max_bytes=_LIMIT, reject_symlink_parents=True)
            archive = stage / f"outputs/package/codex-agent-{version}.tgz"
            with verified_tooling_capture(Path(tooling["evidence"]), root, Path(tooling["publicKey"]),
                    required_trust_domain=tooling["requiredTrustDomain"],
                    keyring=Path(tooling["keyring"]) if tooling["keyring"] is not None else None,
                    keys_directory=Path(tooling["keysDirectory"]) if tooling["keysDirectory"] is not None else None,
                    policy_revision=producer["commit"]) as jar:
                command = [str(java), "-cp", str(jar), "JavaScriptSdkPackageMain", version,
                    str(Path(fields["codexAgent.runtimePackageStage"]) / "outputs/adapter"), str(sources),
                    str(Path(fields["codexAgent.contractBinaryStage"]) / "outputs/evidence/canonical-api.json"),
                    str(compatibility), str(private / "LICENSE"), str(private / "THIRD_PARTY_NOTICES.md"),
                    str(private / "work"), str(archive), str(policy)]
                unchanged()
                with (destination / "package.log").open("xb") as log:
                    result = subprocess.run(command, cwd=private, env=environment, stdout=log,
                                            stderr=subprocess.STDOUT, check=False)
                return_code = result.returncode
                if return_code != 0:
                    raise ValueError(f"JavaScript SDK package failed with exit code {return_code}; see {destination / 'package.log'}")
                after_inputs = {row["relativePath"]: row for row in _inventory(private)}
                if (any(after_inputs.get(path) != record for path, record in private_inputs.items())
                        or read_regular_file_bytes(compatibility, reject_symlink_parents=True) != compatibility_bytes):
                    raise ValueError("JavaScript standalone package inputs changed")
                verify_npm_sdk_compatibility(archive, compatibility,
                    stage / "outputs/evidence/sdk-compatibility-archive.json", sdk_version=version)
                write_output_manifest(stage, "sdk", "javascript", "package", "node", version,
                                      {"evidence": "outputs/evidence", "package": "outputs/package"})
                unchanged()
    except OSError as error:
        launch_error = str(error)
        raise
    finally:
        write_canonical_json(destination / "execution.json", {"schemaVersion": 1,
            "producer": dict(producer), "buildKey": build_key, "command": command,
            "workingDirectory": working_directory, "packageJava": str(java),
            "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started})
        if (read_regular_file_bytes(java, max_bytes=_LIMIT, reject_symlink_parents=True) != java_bytes
                or read_regular_file_bytes(policy, max_bytes=65536, reject_symlink_parents=True) != policy_bytes):
            raise ValueError("JavaScript package Java or codec policy changed")
        unchanged()


def execute(
    plan: Mapping[str, Any], *, producer: Mapping[str, Any], sdk_version: str,
    trust_domain: str, repository_root: Path, destination: Path,
    predecessor: Callable[[str, str, str, str], Mapping[str, Any]],
    environ: Mapping[str, str], compatibility_request: Path | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None, java_executable: Path | None = None,
) -> dict[str, Any]:
    """Package with signed tooling; validate with the fixed Gradle route. Never admit a shard."""
    from native_wrappers import HOSTS, host_classifier
    from product_reuse import (
        _prepare_destination, _runtime_worker_checkout, _runtime_worker_command,
        _runtime_worker_environment,
        _worker_process_environment,
    )

    require_exact_keys(plan, PHASE_PLAN_KEYS, "JavaScript SDK phase plan")
    if require_integer(plan["schemaVersion"], "JavaScript SDK plan schema", 1) != 1:
        raise ValueError("Unsupported JavaScript SDK plan schema")
    elected_route = route(plan)
    require_sha256(plan["buildKey"], "Elected JavaScript SDK build key")
    validate_producer(producer, "Elected JavaScript SDK producer")
    require_semver(sdk_version, "Elected SDK version")
    if trust_domain not in {"development", "release"}:
        raise ValueError("Invalid elected SDK trust domain")
    if HOSTS[host_classifier()][2:4] != (elected_route["runnerOs"], elected_route["runnerArch"]):
        raise ValueError("JavaScript SDK worker actual host differs from its elected route")
    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination).absolute()
    stage = root / f"codex-agent-sdk/build/product-stage/sdk/javascript/{plan['phase']}"
    if destination.exists() or destination.is_symlink() or stage.exists() or stage.is_symlink():
        raise ValueError("JavaScript SDK worker requires fresh diagnostic and product outputs")
    if plan["phase"] == "package":
        require_exact_keys(sdk_validation_tooling, {"evidence", "publicKey", "javaExecutable",
            "requiredTrustDomain", "keyring", "keysDirectory"}, "JavaScript package caller tooling")
        if (not isinstance(java_executable, Path) or not java_executable.is_absolute()
                or java_executable.name != "java" or java_executable.resolve(strict=True) != java_executable):
            raise ValueError("JavaScript package requires an explicit normalized Java executable")
    originals = []

    def original(*identity):
        value = predecessor(*identity)
        original_stage = Path(value["stage"])
        original_inventory = _inventory(original_stage)
        receipt_path = Path(value["receiptPath"])
        raw = read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
        receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
        if receipt != value["receipt"] or tuple(receipt[key] for key in (
                "product", "component", "phase", "target")) != identity:
            raise ValueError("JavaScript SDK predecessor differs from its original receipt")
        if identity[0] == "sdk" and receipt["productVersion"] != sdk_version:
            raise ValueError("Original SDK package version differs from the elected SDK version")
        manifest = verify_output_manifest_identity(value["stage"], *identity, receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("JavaScript SDK predecessor stage differs from its original receipt")
        if (_inventory(original_stage) != original_inventory
                or read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True) != raw):
            raise ValueError("Original JavaScript SDK predecessor changed during verification")
        originals.append((original_stage, original_inventory, receipt_path, raw))
        return value

    request_bytes = None
    request_inventory = {}
    if compatibility_request is not None:
        request_bytes = read_regular_file_bytes(compatibility_request, max_bytes=_LIMIT, reject_symlink_parents=True)
        request_inventory = _request_inventory(compatibility_request)
    fields = properties(plan, predecessor=original, compatibility_request=compatibility_request)
    if compatibility_request is not None and (read_regular_file_bytes(
            compatibility_request, max_bytes=_LIMIT, reject_symlink_parents=True) != request_bytes
            or _request_inventory(compatibility_request) != request_inventory):
        raise ValueError("Original JavaScript SDK request changed during property mapping")
    inputs = [path for tree, _, receipt, _ in originals for path in (tree, receipt)]
    if compatibility_request is not None:
        inputs.extend((compatibility_request, *request_inventory))
    _require_capability_output_separate(destination, [stage, *inputs])
    _require_capability_output_separate(stage, inputs)
    if plan["phase"] == "package":
        environment = _worker_process_environment(root, producer, destination, environ)
        wrapper = None
    else:
        environment, wrapper = _runtime_worker_environment(root, producer, destination, environ, build_directory=".")
    _prepare_destination(stage, root).rmdir()
    destination = _prepare_destination(destination, root)
    fields.update({"codexAgent.product": "sdk", "codexAgent.component": "javascript",
        "codexAgent.phase": plan["phase"], "codexAgent.target": "node",
        "codexAgent.candidateCommit": producer["commit"], "codexAgent.candidateTree": producer["tree"]})

    def unchanged():
        _runtime_worker_checkout(root, producer)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("JavaScript SDK private bytecode namespace was modified")
        if any(_inventory(tree) != inventory or read_regular_file_bytes(
                receipt, max_bytes=_LIMIT, reject_symlink_parents=True) != raw
                for tree, inventory, receipt, raw in originals):
            raise ValueError("Original JavaScript SDK worker inputs changed")
        if compatibility_request is not None and (read_regular_file_bytes(
                compatibility_request, max_bytes=_LIMIT, reject_symlink_parents=True) != request_bytes
                or _request_inventory(compatibility_request) != request_inventory):
            raise ValueError("Original SDK compatibility request or inputs changed")

    unchanged()
    if stage.exists() or stage.is_symlink():
        raise ValueError("JavaScript SDK product stage appeared before execution")
    if plan["phase"] == "package":
        _package(root=root, destination=destination, stage=stage, fields=fields, producer=producer,
            version=sdk_version, environment=environment, tooling=sdk_validation_tooling,
            java=java_executable, build_key=plan["buildKey"], unchanged=unchanged)
        verify_output_manifest_identity(stage, "sdk", "javascript", "package", "node", sdk_version)
        output_inventory = _inventory(stage)
        unchanged()
        return {"stage": stage, "diagnostics": destination, "outputInventory": output_inventory}
    command = _runtime_worker_command(wrapper, fields, environment, build_directory=".")
    started = time.monotonic_ns()
    return_code, launch_error = None, None
    try:
        with (destination / "gradle.log").open("xb") as log:
            process = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                     stderr=subprocess.STDOUT, check=False)
            return_code = process.returncode
    except OSError as error:
        launch_error = str(error)
        raise
    finally:
        write_canonical_json(destination / "execution.json", {"schemaVersion": 1,
            "producer": dict(producer), "buildKey": plan["buildKey"], "command": command,
            "workingDirectory": str(root),
            "returnCode": return_code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started})
        unchanged()
    if return_code != 0:
        raise ValueError(f"JavaScript SDK phase failed with exit code {return_code}; see {destination / 'gradle.log'}")
    verify_output_manifest_identity(stage, "sdk", "javascript", plan["phase"], "node", sdk_version)
    output_inventory = _inventory(stage)
    unchanged()
    return {"stage": stage, "diagnostics": destination, "outputInventory": output_inventory}
