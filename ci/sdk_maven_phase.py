"""Execute four fixed Maven producers; caller owns admission and finalization.

Core binary compiles the existing complete KMP publication on macOS ARM64;
Android binary compiles its AAR on Linux x64 using a preprovisioned archive.
Package phases only decorate imported binaries on Linux x64. Host checks are
execution constraints, not independently observed hosted/toolchain authority.
"""

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
from products.sdk_validation_inputs import _request_inventory
from products.signing_isolation import require_no_signing_secret
from sdk_ios_binary import _directory, _file
from sdk_ios_package import _record


_TARGETS = {"sdk-core": "common", "sdk-android": "android"}
_LIMIT = 512 * 1024 * 1024


def execute(plan, *, producer, sdk_version, repository_root, destination, environ,
            contract_metadata=None, verified_contract_handoff=None, sdk_binary=None,
            compatibility_request=None, android_runtime_archive=None):
    """Run only root ciProductPhase, retaining raw success and failure diagnostics.

    Records and handoffs must already be authenticated by the caller. This leaf
    checks exact identity/content pairing but performs no planner, signer or
    receipt finalization. No arbitrary command, dependency or checksum override.
    """
    require_no_signing_secret(environ)
    selected = require_exact_keys(plan, PHASE_PLAN_KEYS, "Maven SDK phase plan")
    component, phase, target = (selected[name] for name in ("component", "phase", "target"))
    if (require_integer(selected["schemaVersion"], "Maven SDK plan schema", 1) != 1
            or selected["product"] != "sdk" or component not in _TARGETS
            or phase not in {"binary", "package"} or target != _TARGETS[component]
            or PhaseInstanceId("sdk", component, phase, target) not in PHASE_INSTANCE_IDS
            or type(selected["inputs"]) is not dict):
        raise ValueError("Unsupported Maven SDK producer identity")
    require_sha256(selected["buildKey"], "Maven SDK elected build key")
    current = validate_producer(producer, "Maven SDK producer")
    version = require_semver(sdk_version, "Maven SDK version")
    plan_bytes, producer_bytes = canonical_json_bytes(plan), canonical_json_bytes(producer)
    root, destination = Path(repository_root).resolve(strict=True), Path(destination).absolute()
    fields = {"codexAgent.product": "sdk", "codexAgent.component": component,
        "codexAgent.phase": phase, "codexAgent.target": target, "codexAgent.sdkVersion": version,
        "codexAgent.candidateCommit": current["commit"], "codexAgent.candidateTree": current["tree"]}
    trees, files, records = {}, {}, []
    compatibility = {}

    if phase == "binary":
        if (contract_metadata is None or verified_contract_handoff is None
                or sdk_binary is not None or compatibility_request is not None
                or (android_runtime_archive is None) != (component == "sdk-core")):
            raise ValueError("Maven SDK binary requires only its exact Contract and component inputs")
        contract = _record(contract_metadata, ("contract", "contract", "metadata", "common"),
                           "Caller authenticated Contract metadata")
        records.append((contract_metadata, canonical_json_bytes(contract_metadata["receipt"])))
        trees["contract"] = contract[1]
        files["contractReceipt"] = contract[2]
        handoff = _directory(verified_contract_handoff, "Caller verified Contract handoff")
        trees["handoff"] = handoff
        bundles = [entry for entry in contract[-1]["outputs"] if entry["kind"] == "contract-bundle"]
        stem = "codex-agent-contract-" + contract[-1]["productVersion"]
        if len(bundles) != 1 or Path(bundles[0]["relativePath"]).name != stem + ".zip":
            raise ValueError("Maven SDK binary requires its single exact Contract bundle")
        payload = _file(handoff / (stem + ".zip"), "Verified Contract payload", limit=_LIMIT)
        if read_regular_file_bytes(payload, max_bytes=_LIMIT, reject_symlink_parents=True) != \
                read_regular_file_bytes(contract[1] / bundles[0]["relativePath"], max_bytes=_LIMIT,
                                        reject_symlink_parents=True):
            raise ValueError("Maven SDK Contract handoff differs from its exact metadata bundle")
        fields.update({"codexAgent.contractPayload": str(payload),
            "codexAgent.contractMetadataReceipt": str(contract[2]),
            "codexAgent.contractVersion": contract[-1]["productVersion"]})
        for property_name, filename in (("contractAttestation", stem + ".attestation.json"),
                                       ("contractAttestationSignature", stem + ".attestation.sig"),
                                       ("contractPublicKey", "public-key.pub")):
            fields["codexAgent." + property_name] = str(_file(handoff / filename, "Verified " + property_name))
        if component == "sdk-android":
            files["androidArchive"] = _file(android_runtime_archive, "Preprovisioned Android Runtime archive", limit=_LIMIT)
            # The existing producer enforces all three tracked gradle.properties
            # pins; supplying the archive prevents its optional HTTPS fallback.
            fields["codexAgent.codexArchiveFile"] = str(files["androidArchive"])
    else:
        if (sdk_binary is None or compatibility_request is None or contract_metadata is not None
                or verified_contract_handoff is not None or android_runtime_archive is not None):
            raise ValueError("Maven SDK package requires only its binary and compatibility request")
        binary = _record(sdk_binary, ("sdk", component, "binary", target), "Caller authenticated SDK binary")
        if binary[-1]["productVersion"] != version:
            raise ValueError("Maven SDK binary differs from the elected SDK version")
        records.append((sdk_binary, canonical_json_bytes(sdk_binary["receipt"])))
        trees["binary"], files["binaryReceipt"] = binary[1], binary[2]
        files["compatibility"] = _file(compatibility_request, "Caller SDK compatibility request")
        compatibility = _request_inventory(files["compatibility"])
        fields["codexAgent.sdkCoreBinaryStageRoot" if component == "sdk-core"
               else "codexAgent.sdkAndroidBinaryStageRoot"] = str(binary[1])
        fields["codexAgent.sdkCompatibilityRequest"] = str(files["compatibility"])

    tree_before = {name: _inventory(path, allow_empty=True) for name, path in trees.items()}
    file_before = {name: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
                   for name, path in files.items()}
    sdk_build = root / "codex-agent-sdk/build"
    stage = ((root / "build") if phase == "binary" else sdk_build) / f"product-stage/sdk/{component}/{phase}"
    owned = [stage]
    if phase == "package":
        owned.extend((sdk_build / f"imported-sdk-binary-stages/{current['tree']}/{component}",
                      sdk_build / f"sdk-compatibility/{current['tree']}"))
    elif component == "sdk-android":
        owned.append(root / "codex-agent-runtime-android/build/generated/codex-runtime/main")
    outputs = [destination, *owned]
    originals = [*trees.values(), *files.values(), *compatibility]
    for index, output in enumerate(outputs):
        _require_capability_output_separate(output, originals)
        _require_capability_output_separate(output, outputs[index + 1:])
        if (root not in output.parents or output.resolve(strict=False) != output
                or output.exists() or output.is_symlink()):
            raise ValueError("Maven SDK execution requires fresh normalized task-owned outputs inside checkout")

    expected_host = "macos-arm64" if (component, phase) == ("sdk-core", "binary") else "linux-x64"
    if host_classifier() != expected_host:
        raise ValueError("Maven SDK producer requires its actual fixed host: " + expected_host)

    def unchanged():
        require_no_signing_secret(environ)
        if (canonical_json_bytes(plan) != plan_bytes or canonical_json_bytes(producer) != producer_bytes
                or any(canonical_json_bytes(record["receipt"]) != raw for record, raw in records)
                or any(_inventory(path, allow_empty=True) != tree_before[name] for name, path in trees.items())
                or any(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != file_before[name]
                       for name, path in files.items())
                or (compatibility_request is not None and _request_inventory(files["compatibility"]) != compatibility)):
            raise ValueError("Original Maven SDK input changed during execution")
        _runtime_worker_checkout(root, current)
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("Maven SDK private bytecode namespace was modified")

    unchanged()
    environment, wrapper = _runtime_worker_environment(root, current, destination, environ, build_directory=".")
    for output in owned:
        _prepare_destination(output, root).rmdir()
    destination = _prepare_destination(destination, root)
    unchanged()
    command = _runtime_worker_command(wrapper, fields, environment, build_directory=".")
    started = time.monotonic_ns()
    return_code, launch_error = None, None
    try:
        with (destination / "gradle.log").open("xb") as log:
            try:
                result = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                        stderr=subprocess.STDOUT, check=False)
                return_code = result.returncode
            except OSError as error:
                launch_error = str(error)
                raise
            finally:
                write_canonical_json(destination / "execution.json", {
                    "schemaVersion": 1, "producer": dict(current), "buildKey": selected["buildKey"],
                    "command": command, "returnCode": return_code, "launchError": launch_error,
                    "elapsedNs": time.monotonic_ns() - started,
                })
        if return_code != 0:
            raise ValueError(f"Maven SDK phase failed with exit code {return_code}; see {destination / 'gradle.log'}")
        verify_output_manifest_identity(stage, "sdk", component, phase, target, version)
        output_inventory = _inventory(stage)
        diagnostics_inventory = _inventory(destination, allow_empty=True)
        unchanged()
        if (_inventory(stage) != output_inventory
                or _inventory(destination, allow_empty=True) != diagnostics_inventory):
            raise ValueError("Maven SDK output changed during verification")
        return {"stage": stage, "diagnostics": destination, "outputInventory": output_inventory}
    finally:
        unchanged()
