"""Run the elected C# SDK binary producer from authenticated artifact inputs."""

from pathlib import Path
import subprocess
import sys
import time

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from native_wrappers import host_classifier
from product_reuse import (
    _prepare_destination, _runtime_worker_checkout, _runtime_worker_command,
    _runtime_worker_environment,
)
from products.inventory import (
    canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_semver, require_sha256, write_canonical_json,
)
from products.receipt import validate_producer, verify_output_manifest_identity
from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS
from products.sdk_native_metadata import _inventory
from products.sdk_package import _require_capability_output_separate
from products.sdk_csharp_binary import verify_csharp_binary_stage
from products.sdk_dotnet_toolchain import verify_sdk_dotnet_toolchain
from products.sdk_validation_inputs import _request_inventory
from products.signing_isolation import require_no_signing_secret
from sdk_ios_package import _record


_LIMIT = 512 * 1024 * 1024
_IDENTITY = PhaseInstanceId("sdk", "csharp", "binary", "desktop")
_FILES = ("CodexAgent.dll", "CodexAgent.pdb", "CodexAgent.xml", "CodexAgent.deps.json",
          "sdk-compatibility.json", "sdk-runtime-root.pub")


def execute(plan, *, producer, sdk_version, contract_metadata, verified_contract_handoff,
            compatibility_request, repository_root, destination, environ):
    """Execute one Gradle phase; caller owns source admission and receipt publication."""
    require_no_signing_secret(environ)
    selected = require_exact_keys(plan, PHASE_PLAN_KEYS, "C# binary phase plan")
    if (require_integer(selected["schemaVersion"], "C# binary plan schema", 1) != 1
            or tuple(selected[name] for name in ("product", "component", "phase", "target")) != (
                "sdk", "csharp", "binary", "desktop")
            or _IDENTITY not in PHASE_INSTANCE_IDS):
        raise ValueError("Unsupported C# binary producer identity")
    require_sha256(selected["buildKey"], "C# elected build key")
    current = validate_producer(producer, "C# binary producer")
    version = require_semver(sdk_version, "C# SDK version")
    root, destination = Path(repository_root).resolve(strict=True), Path(destination).absolute()
    dotnet_profile = root / "gradle/release/toolchains/sdk/csharp.json"
    verify_sdk_dotnet_toolchain(dotnet_profile)
    contract = _record(contract_metadata, ("contract", "contract", "metadata", "common"),
                       "Caller authenticated Contract metadata")
    require_semver(contract[-1]["productVersion"], "Contract version")
    handoff, request = Path(verified_contract_handoff), Path(compatibility_request)
    if not handoff.is_absolute() or not request.is_absolute():
        raise ValueError("C# binary inputs must be explicit absolute paths")
    bundles = [item for item in contract[-1]["outputs"] if item["kind"] == "contract-bundle"]
    stem = "codex-agent-contract-" + contract[-1]["productVersion"]
    if len(bundles) != 1 or Path(bundles[0]["relativePath"]).name != stem + ".zip":
        raise ValueError("C# binary requires one exact Contract payload")
    payload = handoff / (stem + ".zip")
    if (read_regular_file_bytes(payload, max_bytes=_LIMIT, reject_symlink_parents=True)
            != read_regular_file_bytes(contract[1] / bundles[0]["relativePath"],
                                       max_bytes=_LIMIT, reject_symlink_parents=True)):
        raise ValueError("C# binary Contract handoff differs from original metadata payload")
    properties = {
        "codexAgent.product": "sdk", "codexAgent.component": "csharp",
        "codexAgent.phase": "binary", "codexAgent.target": "desktop",
        "codexAgent.sdkVersion": version,
        "codexAgent.candidateCommit": current["commit"],
        "codexAgent.candidateTree": current["tree"],
        "codexAgent.contractVersion": contract[-1]["productVersion"],
        "codexAgent.contractPayload": str(payload),
        "codexAgent.contractMetadataReceipt": str(contract[2]),
        "codexAgent.contractAttestation": str(handoff / (stem + ".attestation.json")),
        "codexAgent.contractAttestationSignature": str(handoff / (stem + ".attestation.sig")),
        "codexAgent.contractPublicKey": str(handoff / "public-key.pub"),
        "codexAgent.sdkCompatibilityRequest": str(request),
        "codexAgent.csharpDotnetProfile": str(dotnet_profile),
    }
    inputs = [contract[1], contract[2], handoff, request, dotnet_profile,
              *_request_inventory(request)]
    stage = root / "codex-agent-sdk/build/product-stage/sdk/csharp/binary"
    _require_capability_output_separate(stage, [destination])
    for output in (stage, destination):
        _require_capability_output_separate(output, inputs)
        if (root not in output.parents or output.resolve(strict=False) != output
                or output.exists() or output.is_symlink()):
            raise ValueError("C# binary requires fresh normalized task-owned outputs")
    if host_classifier() != "linux-x64":
        raise ValueError("C# binary producer requires the Linux x64 host")
    tree_inventory = {"contract": _inventory(contract[1]), "handoff": _inventory(handoff)}
    files = {"receipt": read_regular_file_bytes(contract[2], max_bytes=_LIMIT, reject_symlink_parents=True),
             "request": read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True),
             "dotnetProfile": read_regular_file_bytes(dotnet_profile, max_bytes=4096,
                                                      reject_symlink_parents=True)}
    request_inventory = _request_inventory(request)
    plan_bytes, producer_bytes = canonical_json_bytes(plan), canonical_json_bytes(producer)

    def unchanged():
        require_no_signing_secret(environ)
        _runtime_worker_checkout(root, current)
        if (canonical_json_bytes(plan) != plan_bytes or canonical_json_bytes(producer) != producer_bytes
                or _inventory(contract[1]) != tree_inventory["contract"]
                or _inventory(handoff) != tree_inventory["handoff"]
                or read_regular_file_bytes(contract[2], max_bytes=_LIMIT, reject_symlink_parents=True) != files["receipt"]
                or read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True) != files["request"]
                or read_regular_file_bytes(dotnet_profile, max_bytes=4096,
                                           reject_symlink_parents=True) != files["dotnetProfile"]
                or _request_inventory(request) != request_inventory):
            raise ValueError("Original C# binary inputs changed during execution")
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("C# binary private bytecode namespace changed")

    unchanged()
    environment, wrapper = _runtime_worker_environment(root, current, destination, environ, build_directory=".")
    _prepare_destination(stage, root).rmdir()
    destination = _prepare_destination(destination, root)
    command = _runtime_worker_command(wrapper, properties, environment, build_directory=".")
    unchanged()
    started = time.monotonic_ns()
    code, launch_error = None, None
    try:
        with (destination / "gradle.log").open("xb") as log:
            result = subprocess.run(command, cwd=root, env=environment,
                                    stdout=log, stderr=subprocess.STDOUT, check=False)
            code = result.returncode
    except OSError as error:
        launch_error = str(error)
        raise
    finally:
        write_canonical_json(destination / "execution.json", {
            "schemaVersion": 1, "producer": dict(current), "buildKey": selected["buildKey"],
            "command": command, "returnCode": code, "launchError": launch_error,
            "elapsedNs": time.monotonic_ns() - started,
        })
        unchanged()
    if code != 0:
        raise ValueError(f"C# binary failed with exit code {code}; see {destination / 'gradle.log'}")
    manifest = verify_output_manifest_identity(stage, "sdk", "csharp", "binary", "desktop", version)
    names = {item["relativePath"] for item in manifest["outputs"]}
    expected = {f"outputs/csharp/{name}" for name in _FILES}
    if names != expected or {item["kind"] for item in manifest["outputs"]} != {"csharp-binary"}:
        raise ValueError("C# binary output has unexpected files or kinds")
    inventory = _inventory(stage)
    unchanged()
    return {"stage": stage, "diagnostics": destination, "outputInventory": inventory}
