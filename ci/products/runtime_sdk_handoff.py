"""Forward a fully verified original Runtime release carrier into existing S858.

SDK version/ranges and the public policy are caller inputs. This does not elect
products, sign, rebuild, or promote transported caller provenance to authority.
The complete original carrier remains external to the standard SDK input tree.
"""

from pathlib import Path
import tempfile

from .inventory import (
    canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_regular_directory, require_sha256,
)
from .registry import NATIVE_TARGETS, PhaseInstanceId
from .runtime_aggregate_handoff import _public_policy, verified_runtime_aggregate_handoff
from .sdk_inputs import stage_sdk_inputs
from .sdk_release_selection import (
    require_sdk_contract_version, require_sdk_release_selection, require_sdk_runtime_compatibility_policy,
)


def stage_runtime_sdk_handoff(handoff_root: Path, destination: Path, *,
                              sdk_version: str, compatible_release_range: str,
                              compatible_runtime_compatibility_range: str,
                              keyring: Path, keys_directory: Path,
                              selection_repository_root: Path | None = None,
                              selection_revision: str | None = None,
                              expected_contract_payload_sha256: str | None = None) -> dict:
    """Publish standard SDK inputs only after full original/policy rechecks.

    The optional caller digest binds Contract payload content, not receipt or
    producer identity, and never replaces the full carrier authentication.
    """
    handoff_root, destination = Path(handoff_root).absolute(), Path(destination).absolute()
    if keyring is None or keys_directory is None:
        raise ValueError("Runtime SDK handoff requires caller-pinned release policy")
    if (selection_repository_root is None) != (selection_revision is None):
        raise ValueError("SDK release selection requires both repository and exact revision")
    if expected_contract_payload_sha256 is not None:
        require_sha256(expected_contract_payload_sha256, "Expected Contract payload SHA-256")
    sources = (handoff_root, Path(keyring).absolute(), Path(keys_directory).absolute())

    def output_safe():
        for path in (destination, *destination.parents):
            if path.is_symlink():
                raise ValueError("Runtime SDK destination has symbolic ancestry")
            if path.exists():
                require_regular_directory(path, "Runtime SDK destination ancestry")
        if destination.exists():
            raise ValueError("Runtime SDK destination must not exist")
        for source in sources:
            for left, right in ((source, destination), (source.resolve(strict=True), destination.resolve())):
                if left == right or left in right.parents or right in left.parents:
                    raise ValueError("Runtime SDK destination overlaps original inputs")

    output_safe()
    with tempfile.TemporaryDirectory(prefix="runtime-sdk-handoff-") as temporary:
        private = Path(temporary).resolve()
        policy = private / "policy"
        paths, original_policy = _public_policy(keyring, keys_directory, policy)
        policy_inventory = regular_file_inventory(policy)
        with verified_runtime_aggregate_handoff(handoff_root,
                keyring=policy / "product-signing-keys.json", keys_directory=policy / "keys") as verified:
            if selection_repository_root is not None:
                require_sdk_release_selection(selection_repository_root, selection_revision,
                    sdk_version=sdk_version, runtime_version=verified["manifest"]["runtimeVersion"])
                require_sdk_contract_version(selection_repository_root, selection_revision,
                    contract_version=verified["manifest"]["contract"]["version"])
                require_sdk_runtime_compatibility_policy(selection_repository_root, selection_revision,
                    compatible_release_range=compatible_release_range,
                    compatible_runtime_compatibility_range=compatible_runtime_compatibility_range)
            root = verified["directory"]
            contract_receipt = verified["receipts"][PhaseInstanceId("contract", "contract", "metadata", "common")]
            if expected_contract_payload_sha256 is not None:
                outputs = [record for record in contract_receipt["outputs"] if record["kind"] == "contract-bundle"]
                if len(outputs) != 1 or outputs[0]["sha256"] != expected_contract_payload_sha256:
                    raise ValueError("Authenticated Runtime Contract payload differs from the selected Contract payload")
            contract_stem = f"codex-agent-contract-{contract_receipt['productVersion']}"
            contract = root / "selected-inputs/contract-input"
            aggregate = root / "aggregate-input"
            runtime_stem = f"codex-agent-runtime-{verified['manifest']['runtimeVersion']}"
            request = {
                "schemaVersion": 1, "sdkVersion": sdk_version,
                "compatibleReleaseRange": compatible_release_range,
                "compatibleRuntimeCompatibilityRange": compatible_runtime_compatibility_range,
                "requiredTrustDomain": "release",
                "contractPayload": str(contract / f"{contract_stem}.zip"),
                "contractMetadataReceipt": str(contract / "execution-closure/receipts/metadata.json"),
                "contractAttestation": str(contract / f"{contract_stem}.attestation.json"),
                "contractAttestationSignature": str(contract / f"{contract_stem}.attestation.sig"),
                "contractPublicKey": str(contract / "public-key.pub"),
                "runtimeManifest": str(aggregate / verified["attestation"]["payload"]["fileName"]),
                "runtimeMetadataReceipt": str(aggregate / "metadata-receipt.json"),
                "runtimeAttestation": str(aggregate / f"{runtime_stem}.attestation.json"),
                "runtimeAttestationSignature": str(aggregate / f"{runtime_stem}.attestation.sig"),
                "runtimePublicKey": str(aggregate / "public-key.pub"),
                "variantBundles": {}, "variantPhaseReceipts": {}, "variantAttestations": {},
                "variantAttestationSignatures": {}, "variantPublicKeys": {},
            }
            for product in ("contract", "runtime"):
                request[f"{product}Keyring"] = str(policy / "product-signing-keys.json")
                request[f"{product}KeysDirectory"] = str(policy / "keys")
            for target in NATIVE_TARGETS:
                native = root / "variant-inputs" / target
                receipt = verified["receipts"][PhaseInstanceId("runtime", target, "metadata", target)]
                # The full reader already enforced this sole original variant output.
                outputs = [record for record in receipt["outputs"] if record["kind"] == "runtime-variant"]
                if len(outputs) != 1:
                    raise ValueError("Runtime SDK handoff requires one original variant bundle")
                bundle = Path(outputs[0]["relativePath"]).name
                stem = Path(bundle).stem
                request["variantBundles"][target] = str(native / bundle)
                request["variantPhaseReceipts"][target] = {
                    phase: str(native / "receipts" / f"{phase}.json")
                    for phase in ("binary", "package", "validation", "metadata")
                }
                request["variantAttestations"][target] = str(native / f"{stem}.attestation.json")
                request["variantAttestationSignatures"][target] = str(native / f"{stem}.attestation.sig")
                request["variantPublicKeys"][target] = str(native / "public-key.pub")
            request_path = private / "request.json"
            request_path.write_bytes(canonical_json_bytes(request))
            result = stage_sdk_inputs(request_path, private / "sdk-inputs")
        # The reader's exit checks must finish before anything is published.
        if (regular_file_inventory(policy) != policy_inventory or any(
                read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True) != original_policy[name]
                for name, path in paths.items())):
            raise ValueError("Runtime SDK caller policy changed during capture")
        output_safe()
        publish_regular_tree(private / "sdk-inputs", destination)
    return result
