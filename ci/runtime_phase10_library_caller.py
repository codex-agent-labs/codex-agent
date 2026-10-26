"""Issue external direct-library trust from the signed original Runtime closure.

This is a local protected-caller seam. It never compiles or repacks reusable
Contract, Runtime variant, or aggregate payloads.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, public_key_fingerprint,
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_sha256, sha256_bytes, snapshot_regular_tree, write_canonical_json,
)
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.runtime_library_authorization import verified_runtime_libraries
from products.sdk_protected_runtime import _original_carrier
from products.sdk_runtime_root import (
    NAMESPACE, PRODUCT_PRINCIPAL, ROOT_NAMESPACE, ROOT_PRINCIPAL,
    _trusted_ssh_keygen, _verify_sshsig, issue_root_delegation,
    validate_root_delegation,
)
from products.signatures import load_keyring, require_active_release_key


_OBSERVATION_TOKENS = frozenset({
    "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN", "ACTIONS_RUNTIME_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
})
_ROOT_SECRET = "CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY"
_PRODUCT_SECRETS = frozenset({
    "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", "SIGNING_IN_MEMORY_KEY",
    "SIGNING_IN_MEMORY_KEY_PASSWORD",
})


def _no_token() -> None:
    if _OBSERVATION_TOKENS & set(os.environ):
        raise ValueError("Runtime library signer must not receive an observation token")


def issue_authenticated_runtime_root_delegation(
    destination: Path, *, keyring: Path, keys_directory: Path,
    root_public_key: Path, expected_root_public_key_sha256: str,
    expected_keyring_sha256: str, expected_keys_inventory_sha256: str,
    root_private_key: Path,
) -> dict:
    """Root-only approval of an exact release keyring; no product key is needed."""
    _no_token()
    if _PRODUCT_SECRETS & set(os.environ):
        raise ValueError("Runtime root delegation must not receive a product signing secret")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime root delegation destination already exists")
    inputs = [Path(path).resolve(strict=True) for path in (
        keyring, keys_directory, root_public_key, root_private_key)]
    output = destination.resolve(strict=False)
    if any(output == path or output in path.parents or path in output.parents for path in inputs):
        raise ValueError("Runtime root delegation output overlaps an input")
    keyring_bytes = read_regular_file_bytes(keyring, max_bytes=1024 * 1024,
                                            reject_symlink_parents=True)
    key_inventory = regular_file_inventory(keys_directory)
    root_bytes = read_regular_file_bytes(root_public_key, max_bytes=4096,
                                         reject_symlink_parents=True)
    if (sha256_bytes(keyring_bytes) != require_sha256(expected_keyring_sha256,
            "protected release keyring digest")
            or sha256_bytes(canonical_json_bytes(key_inventory)) != require_sha256(
                expected_keys_inventory_sha256, "protected release keys inventory")
            or sha256_bytes(root_bytes) != require_sha256(expected_root_public_key_sha256,
                "SDK-pinned root public key digest")):
        raise ValueError("Runtime root delegation inputs differ from independent pins")
    load_keyring(keyring, keys_directory)
    issue_root_delegation(keyring, keys_directory, root_public_key,
                          root_private_key, destination)
    inventory = regular_file_inventory(destination)
    if (read_regular_file_bytes(keyring, max_bytes=1024 * 1024,
            reject_symlink_parents=True) != keyring_bytes
            or regular_file_inventory(keys_directory) != key_inventory
            or read_regular_file_bytes(root_public_key, max_bytes=4096,
                reject_symlink_parents=True) != root_bytes):
        raise ValueError("Runtime root delegation inputs changed during issuance")
    return {"files": inventory,
            "inventorySha256": sha256_bytes(canonical_json_bytes(inventory)),
            "rootPublicKeySha256": expected_root_public_key_sha256,
            "rootFingerprint": public_key_fingerprint(root_bytes)}


def _verify_pinned_delegation(directory: Path, *, root_bytes: bytes,
                              expected_inventory_sha256: str) -> tuple[bytes, list[dict]]:
    inventory = regular_file_inventory(directory)
    if sha256_bytes(canonical_json_bytes(inventory)) != require_sha256(
            expected_inventory_sha256, "protected Runtime delegation inventory"):
        raise ValueError("Runtime root delegation differs from independent inventory pin")
    keyring = directory / "release-keyring.json"
    keyring_bytes = read_regular_file_bytes(keyring, max_bytes=1024 * 1024,
                                            reject_symlink_parents=True)
    policy = load_keyring(keyring, directory / "keys")
    records = ([policy["activeKey"]] if policy["activeKey"] is not None else []) + policy["retiredKeys"]
    expected = {"release-keyring.json", "root-delegation.json", "root-delegation.sig"} | {
        f"keys/{row['keyId']}.pub" for row in records}
    if {row["relativePath"] for row in inventory} != expected:
        raise ValueError("Runtime root delegation has extra or missing files")
    manifest = read_regular_file_bytes(directory / "root-delegation.json",
                                       max_bytes=1024 * 1024, reject_symlink_parents=True)
    delegation = validate_root_delegation(load_canonical_json_bytes(manifest))
    if (delegation["rootFingerprint"] != public_key_fingerprint(root_bytes)
            or delegation["keyringSha256"] != sha256_bytes(keyring_bytes)):
        raise ValueError("Runtime root delegation differs from SDK root or release keyring")
    signature = read_regular_file_bytes(directory / "root-delegation.sig",
                                        max_bytes=1024 * 1024, reject_symlink_parents=True)
    _verify_sshsig(manifest, signature, root_bytes,
                   namespace=ROOT_NAMESPACE, principal=ROOT_PRINCIPAL)
    if regular_file_inventory(directory) != inventory:
        raise ValueError("Runtime root delegation changed during verification")
    return keyring_bytes, inventory


def _write_library_authorizations(libraries, output, delegation, *, release_private_key, public_key, sidecars_only):
    """Shared exact-claim writer; caller owns full source/content/key admission."""
    for target, item in libraries.items():
        library = output / target / item["fileName"]
        library.parent.mkdir(parents=True)
        if sha256_bytes(item["library"]) != item["claim"]["runtimeLibrarySha256"]:
            raise ValueError(f"Runtime library bytes changed during release staging: {target}")
        if not sidecars_only:
            library.write_bytes(item["library"])
            if sha256_bytes(library.read_bytes()) != item["claim"]["runtimeLibrarySha256"]:
                raise ValueError(f"Runtime library bytes changed during release staging: {target}")
        evidence = library.with_name(library.name + ".evidence")
        snapshot_regular_tree(delegation, evidence)
        claim = evidence / "runtime-library-authorization.json"
        write_canonical_json(claim, item["claim"])
        try:
            subprocess.run(
                [_trusted_ssh_keygen(), "-Y", "sign", "-f", str(release_private_key),
                 "-n", NAMESPACE, str(claim)],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ValueError("Runtime direct-library authorization signing failed") from error
        generated = Path(f"{claim}.sig")
        signature = evidence / "runtime-library-authorization.sig"
        signature_bytes = read_regular_file_bytes(generated, max_bytes=1024 * 1024,
                                                  reject_symlink_parents=True)
        _verify_sshsig(claim.read_bytes(), signature_bytes,
                       read_regular_file_bytes(public_key, max_bytes=4096, reject_symlink_parents=True),
                       namespace=NAMESPACE, principal=PRODUCT_PRINCIPAL)
        generated.replace(signature)


def produce_authenticated_runtime_libraries(
    protected_output: Path,
    destination: Path,
    *,
    expected_metadata_receipt_sha256: str,
    expected_build_key: str,
    keyring: Path,
    keys_directory: Path,
    root_public_key: Path,
    expected_root_fingerprint: str,
    expected_root_public_key_sha256: str,
    root_delegation: Path,
    expected_delegation_inventory_sha256: str,
    release_private_key: Path,
    sidecars_only: bool = False,
) -> dict:
    """Sign five claims from a pinned root delegation and signed original handoff."""
    if type(sidecars_only) is not bool:
        raise ValueError("Runtime sidecar-only projection must be boolean")
    _no_token()
    if _ROOT_SECRET in os.environ:
        raise ValueError("Runtime release signer must not receive the SDK root secret")
    protected_output, destination = Path(protected_output), Path(destination)
    expected_metadata_receipt_sha256 = require_sha256(
        expected_metadata_receipt_sha256, "Original Runtime metadata receipt",
    )
    expected_build_key = require_sha256(expected_build_key, "Original Runtime aggregate build key")
    expected_root_fingerprint = require_sha256(expected_root_fingerprint, "SDK-pinned root fingerprint")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime library authorization destination already exists")
    resolved_output = destination.resolve(strict=False)
    resolved_original = protected_output.resolve(strict=True)
    for source in (protected_output, keyring, keys_directory, root_public_key, root_delegation):
        resolved = Path(source).resolve(strict=True)
        if resolved_output == resolved or resolved_output in resolved.parents or resolved in resolved_output.parents:
            raise ValueError("Runtime library authorization output overlaps an input")
        if source != protected_output and (resolved == resolved_original
                                           or resolved in resolved_original.parents
                                           or resolved_original in resolved.parents):
            raise ValueError("Runtime library authorization policy must be external to transported output")
    root_bytes = read_regular_file_bytes(root_public_key, max_bytes=4096, reject_symlink_parents=True)
    if (public_key_fingerprint(root_bytes) != expected_root_fingerprint
            or sha256_bytes(root_bytes) != require_sha256(
                expected_root_public_key_sha256, "SDK-pinned root public key digest")):
        raise ValueError("SDK-pinned Runtime root public key differs from caller pin")
    delegation_before = regular_file_inventory(root_delegation)
    if sha256_bytes(canonical_json_bytes(delegation_before)) != require_sha256(
            expected_delegation_inventory_sha256, "protected Runtime delegation inventory"):
        raise ValueError("Runtime root delegation differs from independent inventory pin")
    before = regular_file_inventory(protected_output, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="rt-p10-library-caller-") as temporary:
        private = Path(temporary).resolve()
        delegation = private / "delegation"
        snapshot_regular_tree(root_delegation, delegation)
        delegated_keyring, delegated_inventory = _verify_pinned_delegation(
            delegation, root_bytes=root_bytes,
            expected_inventory_sha256=expected_delegation_inventory_sha256)
        # The full handoff gate owns its private snapshot and lifetime checks.
        # Do not copy the multi-GB original a second time before entering it.
        carrier = _original_carrier(protected_output, expected_metadata_receipt_sha256, expected_build_key)
        output = private / "libraries"
        with verified_runtime_aggregate_handoff(
            carrier, keyring=keyring, keys_directory=keys_directory,
        ) as verified:
            _original_carrier(verified["directory"], expected_metadata_receipt_sha256, expected_build_key)
            captured_keyring = verified["indexInputs"]["keyring"]
            captured_keys = verified["indexInputs"]["keys_directory"]
            policy = load_keyring(captured_keyring, captured_keys)
            active, public_key = require_active_release_key(policy, captured_keys)
            if (delegated_keyring != read_regular_file_bytes(captured_keyring,
                    max_bytes=1024 * 1024, reject_symlink_parents=True)
                    or regular_file_inventory(delegation / "keys") !=
                        regular_file_inventory(captured_keys)):
                raise ValueError("Runtime root delegation differs from original release key policy")
            if expected_root_fingerprint == active["fingerprint"]:
                raise ValueError("SDK Runtime root and release signer must be separate keys")
            signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
            signing.update(active)
            libraries = verified_runtime_libraries(verified, signing)
            release_secret = Path(release_private_key).resolve(strict=True)
            if (resolved_output == release_secret or resolved_output in release_secret.parents
                    or release_secret in resolved_output.parents or release_secret == resolved_original
                    or release_secret in resolved_original.parents or resolved_original in release_secret.parents):
                raise ValueError("Runtime library authorization output/transport overlaps a signer key")
            _write_library_authorizations(libraries, output, delegation,
                release_private_key=release_private_key, public_key=public_key, sidecars_only=sidecars_only)
        if (regular_file_inventory(protected_output, allow_empty=True) != before
                or read_regular_file_bytes(root_public_key, max_bytes=4096, reject_symlink_parents=True) != root_bytes
                or regular_file_inventory(root_delegation) != delegation_before
                or regular_file_inventory(delegation) != delegated_inventory):
            raise ValueError("Runtime protected original changed during library authorization")
        inventory = regular_file_inventory(output)
        publish_regular_tree(output, destination, expected_inventory=inventory)
        if regular_file_inventory(destination) != inventory or \
                regular_file_inventory(protected_output, allow_empty=True) != before:
            raise ValueError("Runtime library authorization changed during publication")
        return {"files": inventory, "rootFingerprint": expected_root_fingerprint,
                "rootPublicKeySha256": expected_root_public_key_sha256,
                "delegationInventorySha256": expected_delegation_inventory_sha256,
                "runtimeVersion": verified["manifest"]["runtimeVersion"]}




# Independent Phase9 authorization scope; this does not alter release admission.
_IMPORTED_KIND = "sdk-runtime-library-imported-validation"
_IMPORTED_CONTROL_KEYS = {
    "schemaVersion", "kind", "trustedSourceCommit", "inputManifestSha256",
    "custodyCheckpointSha256", "aggregateBuildKey", "metadataReceiptSha256",
    "aggregateManifestSha256", "contractDigest", "sourceTrustDomain", "libraries",
    "rootDelegationInventorySha256", "inputManifestBytes",
}
_IMPORTED_LIBRARY_KEYS = {
    "target", "componentId", "runtimeLibrarySha256", "bundleSha256", "manifestSha256",
}


def validate_imported_validation_control(raw: bytes, *, expected_sha256: str,
                                         trusted_source_commit: str) -> dict:
    """Decode one independently approved scope; this is not signing authority.

    Workflow source and both protected environments must separately pin this
    exact value. The source-specific original admission gate is still required.
    """
    import re
    from products.inventory import require_exact_keys
    from products.registry import NATIVE_TARGETS

    if (len(raw) > 64 * 1024 or sha256_bytes(raw) != require_sha256(
            expected_sha256, "Protected imported-validation control digest")):
        raise ValueError("Imported-validation control differs from independent pin")
    value = require_exact_keys(load_canonical_json_bytes(raw), _IMPORTED_CONTROL_KEYS,
                               "Imported-validation control")
    if (raw != canonical_json_bytes(value) or type(value["schemaVersion"]) is not int
            or value["schemaVersion"] != 2 or value["kind"] != _IMPORTED_KIND
            or value["sourceTrustDomain"] != "development"
            or type(trusted_source_commit) is not str
            or re.fullmatch(r"[0-9a-f]{40}", trusted_source_commit) is None
            or value["trustedSourceCommit"] != trusted_source_commit):
        raise ValueError("Imported-validation purpose, source or trust domain differs")
    for name in _IMPORTED_CONTROL_KEYS - {
            "schemaVersion", "kind", "trustedSourceCommit", "sourceTrustDomain", "libraries", "inputManifestBytes"}:
        require_sha256(value[name], "Imported-validation " + name)
    if type(value["inputManifestBytes"]) is not int or not 1 <= value["inputManifestBytes"] <= 16 * 1024 * 1024:
        raise ValueError("Imported input manifest length exceeds its bound")
    libraries = value["libraries"]
    if type(libraries) is not list or len(libraries) != len(NATIVE_TARGETS):
        raise ValueError("Imported validation requires exactly five target identities")
    for library in libraries:
        require_exact_keys(library, _IMPORTED_LIBRARY_KEYS, "Imported validation library")
        for name in _IMPORTED_LIBRARY_KEYS - {"target"}:
            require_sha256(library[name], "Imported validation library." + name)
    if [row["target"] for row in libraries] != sorted(NATIVE_TARGETS):
        raise ValueError("Imported validation targets must be exact, sorted and unique")
    return value


@contextmanager
def verified_imported_development_content(root: Path, control_path: Path, *,
        expected_control_sha256: str, trusted_source_commit: str, timings: dict | None = None):
    """Join exact original source mappings with existing full development content gates.

    Local development producers remain local. Hosted originals retain their
    separate controller/private-source mappings. The protected scope authenticates
    exact pre-existing libraries; no product receipt is promoted or rewritten.
    No signing key, network client, producer callback or product task is used.
    """
    from products.aggregate import verify_runtime_aggregate_artifacts
    from products.contract_projection import verify_contract_component_projection
    from products.inventory import (
        require_exact_keys, require_relative_path, require_sorted_unique_records,
        validate_file_record, require_regular_directory,
    )
    from products.receipt import validate_phase_receipt, verify_output_manifest_identity
    from products.registry import NATIVE_TARGETS, PhaseInstanceId
    from products.restore import verification_session, memoized_file_inventory
    from products.runtime_aggregate import _adapter_receipt_identities
    from products.runtime_evidence import desktop_evidence_filename, jvm_evidence_filename, node_evidence_filename
    from products.aggregate import RUNTIME_EVIDENCE_TARGETS
    from products.sdk_compatibility import load_sdk_compatibility_request
    from products.sdk_runtime_content import verify_native_runtime_projection

    timings = {} if timings is None else timings
    started = time.monotonic_ns()
    _no_token()
    if _ROOT_SECRET in os.environ:
        raise ValueError("Imported content verification must not receive the SDK root secret")
    root = Path(root).absolute()
    for parent in (root, *root.parents):
        require_regular_directory(parent, "Imported content ancestry")
    if root.resolve(strict=True) != root:
        raise ValueError("Imported content root must be normalized")
    control_path = Path(control_path)
    control_bytes = read_regular_file_bytes(control_path, max_bytes=64 * 1024, reject_symlink_parents=True)
    control = validate_imported_validation_control(control_bytes,
        expected_sha256=expected_control_sha256, trusted_source_commit=trusted_source_commit)
    manifest_path = root / "runtime-validation-import.json"
    manifest_bytes = read_regular_file_bytes(manifest_path, max_bytes=16 * 1024 * 1024,
                                             reject_symlink_parents=True)
    if len(manifest_bytes) != control["inputManifestBytes"] or sha256_bytes(manifest_bytes) != control["inputManifestSha256"]:
        raise ValueError("Imported original inventory differs from independent control")
    manifest = require_exact_keys(load_canonical_json_bytes(manifest_bytes), {
        "schemaVersion", "kind", "files", "originals", "contractStage",
        "runtimeStageRoot", "custodyCheckpoint", "compatibilityRequest", "rootDelegation", "sourceMappings",
    }, "Imported original inventory")
    if (type(manifest["schemaVersion"]) is not int or manifest["schemaVersion"] != 1
            or manifest["kind"] != _IMPORTED_KIND or manifest_bytes != canonical_json_bytes(manifest)):
        raise ValueError("Imported original inventory schema differs")
    records = require_sorted_unique_records(manifest["files"], "Imported original files")
    if not records or len(records) > 16_384:
        raise ValueError("Imported original inventory exceeds its file bound")
    for row in records:
        validate_file_record(row, "Imported original file", with_kind=False, allow_empty=True)
    if (sum(row["bytes"] for row in records) > 4 * 1024**3
            or any(row["bytes"] > 1024**3 for row in records)
            or "runtime-validation-import.json" in {row["relativePath"] for row in records}):
        raise ValueError("Imported original inventory exceeds its byte or self-inventory bound")
    declared = {row["relativePath"]: row for row in records}

    def path(name):
        relative = require_relative_path(name, "Imported original path")
        result = root / relative
        if result.resolve(strict=True) != result:
            raise ValueError("Imported original path is symbolic")
        return result

    def file(name):
        if name not in declared:
            raise ValueError("Imported original file is outside the exact inventory")
        return path(name)

    def json_file(name):
        return load_canonical_json_bytes(read_regular_file_bytes(file(name),
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))

    with verification_session():
        before = memoized_file_inventory(root, allow_empty=True,
            excluded_paths={"runtime-validation-import.json"})
        if before != records:
            raise ValueError("Imported original bytes differ from the complete declared inventory")
        checkpoint_bytes = read_regular_file_bytes(file(manifest["custodyCheckpoint"]),
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        if sha256_bytes(checkpoint_bytes) != control["custodyCheckpointSha256"]:
            raise ValueError("Imported custody anchor differs from its independent pin")
        checkpoint = load_canonical_json_bytes(checkpoint_bytes)
        retained = checkpoint.get("retainedKeys") if type(checkpoint) is dict else None
        if (type(retained) is not list or len(retained) != len(set(retained))
                or checkpoint.get("retainedKeyCount") != len(retained)):
            raise ValueError("Imported custody anchor has an invalid retained-key inventory")

        native = {(target, phase, target) for target in NATIVE_TARGETS
                  for phase in ("binary", "package", "validation", "metadata")}
        expected = native | set(_adapter_receipt_identities()) | {("runtime-aggregate", "metadata", "aggregate")}
        originals, raw_receipts, ordered = {}, {}, []
        if type(manifest["originals"]) is not list or len(manifest["originals"]) != len(expected):
            raise ValueError("Imported content requires its exact46 Runtime originals")
        for record in manifest["originals"]:
            require_exact_keys(record, {"component", "phase", "target", "receipt", "stage"},
                               "Imported original")
            identity = tuple(record[name] for name in ("component", "phase", "target"))
            if identity not in expected or identity in originals:
                raise ValueError("Imported original phase identity is duplicate or unrelated")
            receipt_path = file(record["receipt"])
            raw = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True)
            receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
            if (raw != canonical_json_bytes(receipt)
                    or tuple(receipt[name] for name in ("product", "component", "phase", "target")) != ("runtime", *identity)
                    or receipt["trustDomain"] != "development" or receipt["buildKey"] not in retained):
                raise ValueError("Imported original receipt identity, trust or custody key differs")
            needs_stage = identity[1] in {"validation", "metadata"} or identity in native and identity[1] == "package"
            if needs_stage != (record["stage"] is not None):
                raise ValueError("Imported original stage scope differs from consumed phases")
            stage = path(record["stage"]) if needs_stage else None
            if stage is not None:
                value = verify_output_manifest_identity(stage, "runtime", *identity, receipt["productVersion"])
                if value["outputs"] != receipt["outputs"]:
                    raise ValueError("Imported phase stage differs from its original receipt")
            originals[identity] = dict(receipt=receipt, receiptPath=receipt_path, stage=stage)
            raw_receipts[identity] = raw
            ordered.append(identity)
        if ordered != sorted(expected):
            raise ValueError("Imported originals must be exactly sorted")
        arguments = load_sdk_compatibility_request(file(manifest["compatibilityRequest"]))
        if (arguments["required_trust_domain"] != "development"
                or any(arguments[name] is not None for name in ("contract_keyring", "contract_keys_directory",
                                                               "runtime_keyring", "runtime_keys_directory"))):
            raise ValueError("Imported content request must retain development trust")

        def contained(value):
            if isinstance(value, Path):
                file(value.relative_to(root).as_posix())
            elif type(value) is dict:
                for item in value.values():
                    contained(item)
        contained(arguments)
        aggregate_original = originals[("runtime-aggregate", "metadata", "aggregate")]
        if (arguments["runtime_metadata_receipt"] != aggregate_original["receiptPath"]
                or aggregate_original["receipt"]["buildKey"] != control["aggregateBuildKey"]
                or sha256_bytes(raw_receipts[("runtime-aggregate", "metadata", "aggregate")]) != control["metadataReceiptSha256"]
                or sha256_bytes(read_regular_file_bytes(arguments["runtime_manifest"], reject_symlink_parents=True)) != control["aggregateManifestSha256"]):
            raise ValueError("Imported aggregate identity differs from independent control")
        timings["inventoryAndOriginalJoins"] = time.monotonic_ns() - started
        scope_started = time.monotonic_ns()
        contract = verify_contract_component_projection(path(manifest["contractStage"]),
            arguments["contract_metadata_receipt"], arguments["contract_attestation"],
            arguments["contract_attestation_signature"], arguments["contract_public_key"],
            expected_trust_domain="development", expected_contract_version=validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(arguments["contract_metadata_receipt"], reject_symlink_parents=True)))["productVersion"],
            required_components=("common", *NATIVE_TARGETS))
        if contract.receipt_value()["contractDigest"] != control["contractDigest"]:
            raise ValueError("Imported Contract differs from approved compatibility identity")
        timings["contractContent"] = time.monotonic_ns() - scope_started
        scope_started = time.monotonic_ns()
        provenance = verify_imported_original_source(root, manifest, [
            *[original["receiptPath"] for original in originals.values()],
            arguments["contract_metadata_receipt"],
        ])
        timings["sourceMappings"] = time.monotonic_ns() - scope_started
        scope_started = time.monotonic_ns()
        runtime_root = path(manifest["runtimeStageRoot"])
        native_projections, reports = {}, {}
        for target in NATIVE_TARGETS:
            phases = {phase: originals[(target, phase, target)]["receiptPath"]
                      for phase in ("binary", "package", "validation", "metadata")}
            if phases != arguments["variant_phase_receipts"][target] or any(
                    originals[(target, phase, target)]["stage"] != runtime_root / target / phase
                    for phase in ("package", "validation")):
                raise ValueError("Imported native phase mapping changes original receipts/stages")
            native_projections[target] = verify_native_runtime_projection(target, runtime_root, phases,
                arguments["variant_bundles"][target], arguments["variant_attestations"][target],
                arguments["variant_attestation_signatures"][target], arguments["variant_public_keys"][target],
                contract.restrict(("common", target)), arguments["contract_payload"], required_trust_domain="development")
            reports[target] = runtime_root / target / "validation/outputs/native" / desktop_evidence_filename(RUNTIME_EVIDENCE_TARGETS[target])
        timings["nativeContent"] = time.monotonic_ns() - scope_started
        scope_started = time.monotonic_ns()
        aggregate = load_canonical_json_bytes(read_regular_file_bytes(arguments["runtime_manifest"],
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        adapter_reports, adapter_evidence = {}, {}
        for component in ("jvm", "node-js", "node-wasm"):
            kind = "jvm-evidence" if component == "jvm" else "node-evidence"
            adapter_reports[component] = {}
            for target in NATIVE_TARGETS:
                evidence_target = RUNTIME_EVIDENCE_TARGETS[target]
                name = (jvm_evidence_filename(evidence_target) if component == "jvm" else
                        node_evidence_filename(evidence_target, "js" if component == "node-js" else "wasm"))
                adapter_reports[component][target] = originals[(component, "validation", target)]["stage"] / "outputs" / kind / name
            adapter_evidence[component] = originals[(component, "metadata", component)]["stage"] / "outputs/evidence" / (component + ".json")
        fields = {name: arguments[name] for name in (
            "contract_payload", "contract_metadata_receipt", "contract_attestation", "contract_attestation_signature",
            "contract_public_key", "variant_bundles", "variant_phase_receipts", "variant_attestations",
            "variant_attestation_signatures", "variant_public_keys")}
        value = verify_runtime_aggregate_artifacts(arguments["runtime_manifest"],
            aggregate_metadata_receipt=arguments["runtime_metadata_receipt"],
            aggregate_attestation=arguments["runtime_attestation"],
            aggregate_attestation_signature=arguments["runtime_attestation_signature"],
            aggregate_public_key=arguments["runtime_public_key"], **fields,
            variant_validation_evidence=reports, adapter_report_files=adapter_reports,
            adapter_evidence=adapter_evidence, required_trust_domain="development",
            adapter_receipts=[dict(component=c, phase=p, target=t, receipt=originals[(c,p,t)]["receiptPath"])
                              for c,p,t in _adapter_receipt_identities()],
            runtime_maven_files=[{**{name: row[name] for name in ("path", "role", "component")},
                "file": aggregate_original["stage"] / "outputs" / row["path"]} for row in aggregate["runtimeMavenFiles"]])
        expected_variants = [{name: row[name] for name in ("target", "componentId", "bundleSha256", "manifestSha256")}
                             for row in control["libraries"]]
        if sorted(value["variants"], key=lambda row: row["target"]) != expected_variants:
            raise ValueError("Imported variant identity differs from approved libraries")

        timings["aggregateContent"] = time.monotonic_ns() - scope_started

        def unchanged():
            if (read_regular_file_bytes(control_path, max_bytes=64 * 1024, reject_symlink_parents=True) != control_bytes
                    or read_regular_file_bytes(manifest_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != manifest_bytes
                    or memoized_file_inventory(root, allow_empty=True, excluded_paths={"runtime-validation-import.json"}) != before):
                raise ValueError("Imported original or protected control changed during verification")
        unchanged()
        yield {"manifest": value, "attestation": load_canonical_json_bytes(read_regular_file_bytes(
                arguments["runtime_attestation"], reject_symlink_parents=True)),
            "nativeRuntimeProjections": native_projections,
            "originalPhases": {PhaseInstanceId("runtime", *identity): original for identity, original in originals.items()},
            "indexInputs": {"manifest": arguments["runtime_manifest"], "attestation": arguments["runtime_attestation"],
                "variant_bundles": arguments["variant_bundles"], "variant_attestations": arguments["variant_attestations"]},
            "originalProvenance": provenance, "control": control, "rootDelegation": path(manifest["rootDelegation"]),
            "elapsedNsByScope": timings}
        scope_started = time.monotonic_ns()
        unchanged()
        timings["finalLifetime"] = time.monotonic_ns() - scope_started
        timings["fullContentGate"] = time.monotonic_ns() - started


def verify_imported_original_source(directory: Path, manifest: dict, phase_receipts: list[Path]) -> dict:
    """Authenticate flat original source mappings without executing imported code.

    The independently pinned import manifest supplies data only. Four fixed
    observation policies cover the nine already accepted hosted originals.
    Every producer receipt is preserved; local producers remain local.
    """
    import hashlib
    import ntpath
    import posixpath
    import re
    from products.inventory import (require_exact_keys,require_relative_path,verified_zip_contents,
        load_json_bytes)
    from products.receipt import validate_phase_receipt,validate_producer,output_inventory_digest
    from products.toolchain import load_toolchain_profile_bytes,validate_producer_observation,verify_toolchain_profile
    from products.registry import PhaseInstanceId
    from product_reuse import _worker_upload_zip_limits

    root=Path(directory).absolute();declared={row['relativePath']:row for row in manifest['files']}
    def file(name):
        name=require_relative_path(name,'Original mapping file')
        if name not in declared:raise ValueError('Original mapping refers outside the pinned inventory')
        return root/name
    def raw(name):return read_regular_file_bytes(file(name),max_bytes=32*1024*1024,reject_symlink_parents=True)
    def read(name):return load_json_bytes(raw(name))
    def one(values):
        value,=values;return value
    receipts={}
    for path in phase_receipts:
        data=read_regular_file_bytes(path,reject_symlink_parents=True)
        receipts[sha256_bytes(data)]=validate_phase_receipt(load_canonical_json_bytes(data))
    mappings=manifest['sourceMappings']
    if type(mappings) is not list or len(mappings)!=9:raise ValueError('Exactly nine hosted original mappings required')
    expected={('windows-x64','binary','windows-x64'),('windows-x64','validation','windows-x64'),
        ('macos-x64','validation','macos-x64'),*((c,'validation',t) for c in ('jvm','node-js','node-wasm') for t in ('macos-x64','windows-x64'))}
    accepted=set(); source_files={};archives={}
    source_git={path for path in declared if path.startswith('source-git/')}
    fixed={'source-git/HEAD','source-git/config','source-git/refs/heads/imported'}
    if not fixed<=source_git or any(path not in fixed and re.fullmatch(r'source-git/objects/[0-9a-f]{2}/[0-9a-f]{38}',path) is None for path in source_git):
        raise ValueError('Only exact consumed loose Git objects and minimal bare controls are allowed')
    if raw('source-git/HEAD')!=b'ref: refs/heads/imported'+bytes([10]) or raw('source-git/config')!=b'[core]'+bytes([10,9])+b'repositoryformatversion = 0'+bytes([10,9])+b'bare = true'+bytes([10]):
        raise ValueError('Source Git controls must not contain hooks, alternates or extra configuration')
    if re.fullmatch(rb'[0-9a-f]{40}\n',raw('source-git/refs/heads/imported')) is None:raise ValueError('Source Git head must be exact')
    environment={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    environment.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_DIR=str(root/'source-git'))
    def git_object(kind,identity):
        if re.fullmatch('[0-9a-f]{40}',identity) is None:raise ValueError('Exact original Git identity required')
        value=subprocess.check_output(['git','--no-replace-objects','cat-file',kind,identity],cwd=root,env=environment)
        if hashlib.sha1(kind.encode()+b' '+str(len(value)).encode()+bytes([0])+value).hexdigest()!=identity:
            raise ValueError('Original Git object content identity differs')
        return value
    def commit_tree(commit,tree):
        if git_object('commit',commit).splitlines()[0]!=('tree '+tree).encode():raise ValueError('Original commit/tree differs')
    def git_file(commit,path):
        require_relative_path(path,'Original Git input')
        key=(commit,path)
        if key not in source_files:
            source_files[key]=subprocess.check_output(['git','--no-replace-objects','show',commit+':'+path],cwd=root,env=environment)
        return source_files[key]
    def original_inputs(receipt):
        producer=receipt['producer'];commit_tree(producer['commit'],producer['tree'])
        for entry in receipt['inputs']['inventory']:
            data=git_file(producer['commit'],entry['relativePath'])
            if len(data)!=entry['bytes'] or sha256_bytes(data)!=entry['sha256']:raise ValueError('Original input differs from producer source')
    def step(job,name):
        value=one(v for v in job['steps'] if v['name']==name)
        if (value['status'],value['conclusion'])!=('completed','success') or not job['started_at']<=value['started_at']<=value['completed_at']<=job['completed_at']:
            raise ValueError('Original successful execution/upload window differs')
        return value
    for mapping in mappings:
        require_exact_keys(mapping,{'kind','receipt','controller','metadata','artifacts','upstreamReceipts','workflowSha256','helperPath','helperSha256'},'Original source mapping')
        receipt_bytes=raw(mapping['receipt']);receipt_digest=sha256_bytes(receipt_bytes)
        if receipt_digest not in receipts:raise ValueError('Source mapping is not an original selected receipt')
        receipt=receipts[receipt_digest];identity=tuple(receipt[k] for k in ('component','phase','target'))
        if identity not in expected or identity in accepted:raise ValueError('Duplicate or unrelated original source mapping')
        accepted.add(identity);component,phase,target=identity
        kind=('windows-binary' if phase=='binary' else 'windows-validation' if component=='windows-x64' else
            'intel-validation' if component=='macos-x64' else 'adapter-validation')
        if mapping['kind']!=kind:raise ValueError('Original observation policy differs')
        controller=require_exact_keys(mapping['controller'],{'commit','tree','workflowEventCommit','jobId'},'Original controller')
        commit_tree(controller['commit'],controller['tree'])
        producer=receipt['producer'];repository='codex-agent-labs/codex-agent';workflow='.github/workflows/portable-reuse-proof.yml'
        if producer['event']!='pull_request' or producer['pullRequest']!=31 or producer['repository']!=repository or producer['workflowPath']!=workflow:
            raise ValueError('Original producer scope differs')
        require_exact_keys(mapping['metadata'],{'run','jobs','artifacts','eventCommit'},'Original official metadata')
        run,jobs,listing=[read(mapping['metadata'][k]) for k in ('run','jobs','artifacts')]
        if (run['id'],run['run_attempt'],run['head_sha'],run['event'],run['path'])!=(producer['runId'],producer['runAttempt'],controller['commit'],'pull_request',workflow):
            raise ValueError('Original run/controller differs')
        if any(run[k]['id']!=1320780624 or run[k]['full_name']!=repository for k in ('repository','head_repository')):
            raise ValueError('Original official repository differs')
        request=one(run['pull_requests'])
        if request['number']!=31 or request['head']['sha']!=controller['commit']:raise ValueError('Original PR head differs')
        if mapping['metadata']['eventCommit'] is not None:
            event=read(mapping['metadata']['eventCommit'])
            if event['sha']!=controller['workflowEventCommit'] or controller['commit'] not in {p['sha'] for p in event['parents']}:
                raise ValueError('Original workflow-event ancestry differs')
        elif kind!='intel-validation':raise ValueError('Original workflow-event observation is missing')
        job_name={'windows-binary':'phase9-runtime-windows-binary','windows-validation':'phase9-native-windows-artifact-validation',
            'intel-validation':'phase9-native-artifact-validation','adapter-validation':'Phase9 adapter collection ('+target+')'}[kind]
        job=one(j for j in jobs['jobs'] if j['name']==job_name)
        label='windows-2025' if target=='windows-x64' else 'macos-26-intel'
        if (job['id'],job['run_id'],job['run_attempt'],job['head_sha'],job['status'],job['conclusion'],job['labels'])!=(controller['jobId'],producer['runId'],producer['runAttempt'],controller['commit'],'completed','success',[label]):
            raise ValueError('Original successful job/host/controller differs')
        execute_name,upload_name={
            'windows-binary':('Execute only the missing canonical-model Windows binary','Preserve original Windows outputs and diagnostics'),
            'windows-validation':('Validate only the preserved Windows package on genuine Windows','Preserve original Windows validation evidence and diagnostics'),
            'intel-validation':('Validate only the preserved Mac x64 package on genuine Intel','Preserve validation evidence and raw diagnostics, never duplicate input bodies'),
            'adapter-validation':('Execute only missing '+component+' validation','Preserve '+component+' outputs before the next component'),
        }[kind]
        execute,upload=step(job,execute_name),step(job,upload_name)
        if execute['completed_at']>upload['started_at']:raise ValueError('Original upload precedes execution')
        helper='ci/tests/'+('phase9_runtime_mutation.py' if kind=='windows-binary' else 'phase9_adapter_validation.py' if kind=='adapter-validation' else 'phase9_native_validation.py')
        if mapping['helperPath']!=helper:raise ValueError('Original helper policy differs')
        if sha256_bytes(git_file(controller['commit'],workflow))!=mapping['workflowSha256'] or sha256_bytes(git_file(controller['commit'],helper))!=mapping['helperSha256']:
            raise ValueError('Reviewed controller workflow/helper differs')
        expected_roles={'phase','shared'} if kind=='adapter-validation' else {'phase'}
        require_exact_keys(mapping['artifacts'],expected_roles,'Original upload roles')
        documents={}
        for role,entry in mapping['artifacts'].items():
            require_exact_keys(entry,{'artifactId','archive','controls'},'Original upload')
            artifact=one(a for a in listing['artifacts'] if a['id']==entry['artifactId'])
            window=step(job,'Preserve shared intake diagnostics without duplicating product bodies') if role=='shared' else upload
            if artifact['workflow_run']!={**artifact['workflow_run'],'id':producer['runId'],'head_sha':controller['commit'],'repository_id':1320780624,'head_repository_id':1320780624} or artifact['expired'] is not False:
                raise ValueError('Original upload repository/run differs')
            if not window['started_at']<=artifact['created_at']<=artifact['updated_at']<=window['completed_at']:raise ValueError('Original artifact lies outside successful upload')
            limits=_worker_upload_zip_limits(PhaseInstanceId('runtime',component,phase,target))
            archive=file(entry['archive']); names=set(entry['controls'])
            # Captured controls are exact original ZIP members; no imported executable is loaded.
            cache_key=(str(archive),artifact['digest'])
            if cache_key not in archives:
                inventory,contents,archive_record=verified_zip_contents(archive,require_sorted=False,allow_empty_members=True,
                    retained_paths=names,max_archive_bytes=limits['max_archive_bytes'],max_central_directory_bytes=limits['max_central_directory_bytes'],
                    max_members=limits['max_members'],max_entry_bytes=limits['max_entry_bytes'],max_total_bytes=limits['max_total_bytes'],max_compression_ratio=200)
                if archive_record['bytes']!=artifact['size_in_bytes'] or archive_record['sha256']!=artifact['digest']:raise ValueError('Official original archive differs')
                archives[cache_key]=(inventory,contents)
            inventory,contents=archives[cache_key]
            if not names<=contents.keys():raise ValueError('Shared original control selection differs')
            for member,path in entry['controls'].items():
                if raw(path)!=contents[member]:raise ValueError('Original control differs from official ZIP member')
            documents[role]={name:load_json_bytes(contents[name]) for name in names if name.endswith('.json')}
            if role=='phase':
                prefix='source/codex-agent-runtime-desktop/build/product-stage/runtime/windows-x64/binary/' if kind=='windows-binary' else 'stage/'
                indexed={r['relativePath']:r for r in inventory}
                if {n for n in indexed if n.startswith(prefix)}!={prefix+r['relativePath'] for r in receipt['outputs']}|{prefix+'output-manifest.json'}:
                    raise ValueError('Original phase output inventory differs')
                for row in receipt['outputs']:
                    if indexed[prefix+row['relativePath']]!={k:v for k,v in {**row,'relativePath':prefix+row['relativePath']}.items() if k!='kind'}:
                        raise ValueError('Original phase member differs from receipt')
        receipt_member='binary-receipt/phase-receipt.json' if kind=='windows-binary' else 'phase-receipt.json'
        if raw(mapping['artifacts']['phase']['controls'][receipt_member])!=receipt_bytes:raise ValueError('Archived original receipt differs from selected receipt')
        phase_docs=documents['phase'];result=phase_docs['result.json'];plan=phase_docs['plan.json']
        if plan['inputs']!=receipt['inputs'] or plan['buildKey']!=receipt['buildKey'] or result['buildKey']!=receipt['buildKey'] or result['receiptSha256']!=receipt_digest:
            raise ValueError('Original plan/result/receipt identity differs')
        original_receipts={name:validate_phase_receipt(load_canonical_json_bytes(raw(path))) for name,path in mapping['upstreamReceipts'].items()}
        if kind=='windows-binary':
            context=phase_docs['hosted-context.json'];execution=phase_docs['binary-execution.json'];election=phase_docs['binary-election.json']
            expected_controller=dict(sourceCommit=controller['commit'],sourceTree=controller['tree'],workflowEventCommit=controller['workflowEventCommit'],runId=producer['runId'],runAttempt=producer['runAttempt'],target=target,role='builder',productExecutions=0,releaseAdmission=False)
            if context['controller']!=expected_controller or result['hostedContext']!=expected_controller or election['hostedContext']!=expected_controller:
                raise ValueError('Original Windows binary controller differs')
            if any(value!=producer for value in (context['fixtureExecution'],result['producer'],execution['producer'],election['producer'])):
                raise ValueError('Windows binary source producer was relabeled')
            for name in ('prepared.json','source-preparation.json'):
                preparation=phase_docs[name]
                if (preparation['sourceCommit'],preparation['sourceTree'],preparation['profileDigest'],preparation['productExecutions'])!=(producer['commit'],producer['tree'],receipt['inputs']['toolchainProfileDigest'],0):raise ValueError('Windows binary source preparation differs')
            observation=validate_producer_observation(phase_docs['toolchain-observation.json'])
            profile_bytes=git_file(producer['commit'],'gradle/release/toolchains/runtime/windows-x64.json')
            if sha256_bytes(profile_bytes)!=receipt['inputs']['toolchainProfileDigest']:raise ValueError('Original Windows toolchain profile differs')
            actual=observation['producer'];verify_toolchain_profile(load_toolchain_profile_bytes(profile_bytes,target),receipt['inputs']['toolchainProfileDigest'],'builder',actual['runner'],{r['name']:r['identity'] for r in actual['tools']},image_provenance=observation['imageProvenance'])
            if execution['returnCode']!=0 or execution['command']!=election['command'] or result['productExecutions']!=1:raise ValueError('Original Windows binary execution differs')
            contract=original_receipts.get('contract')
            if contract is None or context['originalContractProducer']!=contract['producer']:raise ValueError('Original Contract producer differs')
            if plan['inputs']['upstreamArtifacts'][0]['contractProjection']['receiptSha256']!=sha256_bytes(raw(mapping['upstreamReceipts']['contract'])):raise ValueError('Original Contract predecessor differs')
            command=execution['command']
            if not ntpath.isabs(command[0]) or ntpath.basename(command[0]).lower()!='java.exe' or command[1:5]!=['-Xmx64m','-Xms64m','-Dorg.gradle.appname=gradlew','-jar']:raise ValueError('Original Windows builder command differs')
            if command[6]!='-I' or not command[7].replace(chr(92),'/').endswith('/source/codex-agent-runtime-desktop/src/mingwMain/gradle/deterministic-native-link.init.gradle') or command[8:15]!=['--dependency-verification=strict','--no-daemon','--configuration-cache','--configuration-cache-problems=fail','-p','runtime','ciProductPhase'] or command[-3:]!=['--max-workers=2','--console=plain','--info']:raise ValueError('Original Windows build policy differs')
            props=command[15:-3]
            if props!=sorted(props) or any(not v.startswith('-P') or '=' not in v for v in props):raise ValueError('Original Windows properties differ')
            values=dict(v[2:].split('=',1) for v in props)
            if len(values)!=len(props) or any(values['codexAgent.'+k]!=v for k,v in dict(product='runtime',component=target,phase='binary',target=target,contractVersion=contract['productVersion'],runtimeVersion=receipt['productVersion'],candidateCommit=producer['commit'],candidateTree=producer['tree']).items()):raise ValueError('Original Windows input identity differs')
            if (observation['repositoryRevision'],observation['repositoryTree'],observation['profileId'])!=(producer['commit'],producer['tree'],target) or election['profileObservationSha256']!=sha256_bytes(raw(mapping['artifacts']['phase']['controls']['toolchain-observation.json'])):raise ValueError('Original Windows observation identity differs')
            log='binary.log'
        else:
            execution=phase_docs['execution.json'];log='validation.log'
            original_producers={name:r['producer'] for name,r in original_receipts.items()}
            if kind=='adapter-validation':
                shared=documents['shared'];context=shared['context.json'];preparation=shared['preparation.json'];source=shared['source-preparation.json']
                if context['producer']!=dict(producer,commit=controller['commit'],tree=controller['tree']) or context['workflowEventCommit']!=controller['workflowEventCommit']:
                    raise ValueError('Original adapter controller differs')
                if result['verifier']!={'controller':context,'fixtureExecution':producer} or result['originalProducers']!=original_producers:
                    raise ValueError('Original adapter product/predecessor producer differs')
                if (source['sourceCommit'],source['sourceTree'],source['productExecutions'])!=(producer['commit'],producer['tree'],0):raise ValueError('Original adapter source preparation differs')
                election=phase_docs['election.json']
                if election['plan']!=plan or election['controller']!=context or election['fixtureExecution']!=producer or election['originalProducers']!=original_producers or election['command']!=execution['command'] or execution['returnCode']!=0:raise ValueError('Original adapter execution mapping differs')
                if preparation['controller']!=context or preparation['sourcePreparationSha256']!=sha256_bytes(raw(mapping['artifacts']['shared']['controls']['source-preparation.json'])) or preparation['plans'][component]!=plan:raise ValueError('Original adapter preparation differs')
                if shared[target+'-status.json']['components'][component]!='success':raise ValueError('Original adapter collection failed')
            else:
                context=phase_docs['context.json']
                if context!=result['verifier'] or execution['exitCode']!=0:raise ValueError('Original native validation context differs')
                if kind=='intel-validation':
                    if context['producer']!=producer or producer['commit']!=controller['commit']:raise ValueError('Original Intel producer differs')
                    if context['workflowEventCommit']!=controller['workflowEventCommit'] or (context['runnerOS'],context['runnerArch'],context['xcode'].strip())!=('macOS','X64',chr(10).join(('Xcode 26.6','Build version 17F113'))):raise ValueError('Original Intel host differs')
                    if any(v!=result['originalProducer'] for v in original_producers.values()):raise ValueError('Original Intel predecessors were relabeled')
                elif context['fixtureExecution']!=producer or context['controller']['producer']!=dict(producer,commit=controller['commit'],tree=controller['tree']) or result['originalProducers']!=original_producers:
                    raise ValueError('Original Windows validator/source producer differs')
            command=execution['command']
            if execution['elapsedNs']!=result['executionNs']:raise ValueError('Original execution timing differs')
            if kind=='intel-validation':
                if len(command)!=10 or not command[0].endswith('/codex-agent/gradlew') or command[1]!='-p' or not command[2].endswith('/phase9-native-validation/executor') or command[3:8]!=['--offline','--no-daemon','--no-configuration-cache','--max-workers=2','--console=plain'] or not command[8].startswith('-Pphase9.context=') or command[9]!=':codex-agent-runtime-desktop:writeMacosX64RuntimeValidationOutputManifest':raise ValueError('Original Intel executor differs')
                if context['translationProbe']['stdout'].strip() not in ('','0'):raise ValueError('Original Intel execution was translated')
            else:
                executor=phase_docs['executor-context.json'];paths=ntpath if target=='windows-x64' else posixpath
                private=paths.normpath(executor['repositoryRoot']);destination=paths.dirname(private)
                if not paths.isabs(private) or paths.basename(private)!='source':raise ValueError('Original executor source root differs')
                context_path=paths.join(destination,component if kind=='adapter-validation' else '', 'executor-context.json')
                if kind=='windows-validation':
                    observed=context['controller']
                    if observed['workflowEventCommit']!=controller['workflowEventCommit'] or (observed['runnerOS'],observed['runnerArch'])!=('Windows','X64') or not observed['image'] or not observed['imageVersion'] or 'version "17.' not in observed['java']:raise ValueError('Original Windows validator host differs')
                    if observed['msvc']['returnCode'] not in (0,2) or 'Microsoft' not in observed['msvc']['stdout']+observed['msvc']['stderr']:raise ValueError('Original Windows C ABI consumer toolchain differs')
                    if len(command)!=15 or not ntpath.isabs(command[0]) or ntpath.basename(command[0]).lower()!='java.exe' or command[1:5]!=['-Xmx64m','-Xms64m','-Dorg.gradle.appname=gradlew','-jar'] or ntpath.normpath(command[5])!=ntpath.join(private,'gradle','wrapper','gradle-wrapper.jar') or command[6]!='-p' or ntpath.normpath(command[7])!=ntpath.join(destination,'executor') or command[8:13]!=['--offline','--no-daemon','--no-configuration-cache','--max-workers=2','--console=plain'] or command[14]!=':codex-agent-runtime-desktop:writeMingwX64RuntimeValidationOutputManifest':raise ValueError('Original Windows executor differs')
                    if not command[13].startswith('-Pphase9.context=') or ntpath.normpath(command[13].split('=',1)[1])!=ntpath.normpath(context_path) or (executor['producerCommit'],executor['producerTree'])!=(producer['commit'],producer['tree']):raise ValueError('Original Windows executor context differs')
                else:
                    expected_host=('Windows','X64') if target=='windows-x64' else ('macOS','X64')
                    if (context['runnerOS'],context['runnerArch'])!=expected_host or context['target']!=target or 'version "17.' not in context['javaVersion'] or context['nodeVersion']!='v24.18.0' or context['nodeHost']!={'platform':'win32' if target=='windows-x64' else 'darwin','arch':'x64'}:raise ValueError('Original adapter host differs')
                    expected_command=([context['javaExecutable'],'-Xmx64m','-Xms64m','-Dorg.gradle.appname=gradlew','-jar',paths.join(private,'gradle','wrapper','gradle-wrapper.jar')] if target=='windows-x64' else [paths.join(private,'gradlew')])
                    expected_command+=['-p',paths.join(destination,component,'executor'),'--offline','--no-daemon','--no-configuration-cache','--max-workers=1','--console=plain','-Dorg.gradle.jvmargs=-Xmx1536m -Dfile.encoding=UTF-8','-Pphase9.context='+paths.normpath(context_path),':codex-agent-runtime-desktop:writeAdapterRuntimeValidationOutputManifest']
                    if len(command)!=len(expected_command):raise ValueError('Original adapter command arity differs')
                    for actual,expected_arg in zip(command,expected_command,strict=True):
                        if expected_arg.startswith('-Pphase9.context='):
                            if not actual.startswith('-Pphase9.context=') or paths.normpath(actual.split('=',1)[1])!=paths.normpath(expected_arg.split('=',1)[1]):raise ValueError('Original adapter context path differs')
                        elif paths.isabs(expected_arg):
                            if paths.normpath(actual)!=paths.normpath(expected_arg):raise ValueError('Original adapter command path differs')
                        elif actual!=expected_arg:raise ValueError('Original adapter command policy differs')
            if result['passed'] is not True or result['productBuilds']!=0 or result['releaseAdmission'] is not False:raise ValueError('Original validation success scope differs')
            edges=[dict(**{k:r[k] for k in ('product','component','phase','target','buildKey')},outputsDigest=output_inventory_digest(r['outputs'])) for r in original_receipts.values() if r['phase']=='package']
            if sorted(receipt['inputs']['upstreamArtifacts'],key=lambda x:x['component'])!=sorted(edges,key=lambda x:x['component']):raise ValueError('Original validation predecessors differ')
        if execution['logSha256']!=sha256_bytes(raw(mapping['artifacts']['phase']['controls'][log])):raise ValueError('Original execution log differs')
    if accepted!=expected:raise ValueError('An original hosted mapping is missing')
    admitted={sha256_bytes(raw(row['receipt'])) for row in mappings}
    for digest,receipt in receipts.items():
        if receipt['trustDomain']!='development' or receipt['producer']['event']!='local' and digest not in admitted:
            raise ValueError('Unrecognized original producer/trust domain')
        original_inputs(receipt)
    return {'hostedOriginals':len(accepted),'sourceFiles':len(source_files),'originalArchives':len(archives)}


def produce_imported_runtime_libraries(directory: Path, control_path: Path, destination: Path, *,
        expected_control_sha256: str, trusted_source_commit: str, keyring: Path,
        keys_directory: Path, root_public_key: Path, expected_root_public_key_sha256: str,
        release_private_key: Path, timings: dict | None = None) -> dict:
    """Authorize exact genuine development libraries under the stable SDK root.

    These are real exact-library authorizations accepted by compatible SDKs.
    They are not test-only signatures and do not promote development receipts.
    """
    timings = {} if timings is None else timings
    started = time.monotonic_ns()
    _no_token()
    if _ROOT_SECRET in os.environ:
        raise ValueError("Imported library authorization must not receive a root private key")
    directory,destination=Path(directory).absolute(),Path(destination).absolute()
    if destination.exists() or destination.is_symlink():raise ValueError("Authorization destination exists")
    for original in (directory,keyring,keys_directory,root_public_key,release_private_key):
        original=Path(original).resolve(strict=True)
        if destination==original or destination in original.parents or original in destination.parents:
            raise ValueError("Authorization output overlaps an input")
        if original!=directory and (original in directory.parents or directory in original.parents):
            raise ValueError("Imported authorization keys/policy must be outside captured inputs")
    root_bytes=read_regular_file_bytes(root_public_key,max_bytes=4096,reject_symlink_parents=True)
    if sha256_bytes(root_bytes)!=require_sha256(expected_root_public_key_sha256,"Protected SDK root pin"):
        raise ValueError("SDK root public key differs from independent protected pin")
    policy_bytes=read_regular_file_bytes(keyring,max_bytes=1024*1024,reject_symlink_parents=True)
    policy_inventory=regular_file_inventory(keys_directory)
    with tempfile.TemporaryDirectory(prefix='imported-runtime-library-') as temporary:
        output=Path(temporary).resolve()/'libraries'
        with verified_imported_development_content(directory,control_path,
                expected_control_sha256=expected_control_sha256,trusted_source_commit=trusted_source_commit, timings=timings) as verified:
            scope_started = time.monotonic_ns()
            delegated_keyring,delegation_inventory=_verify_pinned_delegation(verified["rootDelegation"],
                root_bytes=root_bytes,expected_inventory_sha256=verified["control"]["rootDelegationInventorySha256"])
            if delegated_keyring!=policy_bytes or regular_file_inventory(verified["rootDelegation"]/'keys')!=policy_inventory:
                raise ValueError("Existing root delegation differs from exact current release-key policy")
            policy=load_keyring(keyring,keys_directory)
            active,public_key=require_active_release_key(policy,keys_directory)
            if active["fingerprint"]==public_key_fingerprint(root_bytes):raise ValueError("Root and product keys must remain separate")
            signing={name:policy[name] for name in ("algorithm","namespace","trustDomain")};signing.update(active)
            timings["delegationPolicy"] = time.monotonic_ns() - scope_started
            scope_started = time.monotonic_ns()
            libraries=verified_runtime_libraries(verified,signing)
            expected=[dict(target=target,componentId=item["claim"]["runtimeIdentity"]["componentId"],
                runtimeLibrarySha256=item["claim"]["runtimeLibrarySha256"],
                bundleSha256=item["claim"]["variantBundleSha256"],manifestSha256=item["claim"]["variantManifestSha256"])
                for target,item in sorted(libraries.items())]
            if expected!=verified["control"]["libraries"]:raise ValueError("Projected exact libraries differ from protected authorization")
            timings["libraryProjection"] = time.monotonic_ns() - scope_started
            scope_started = time.monotonic_ns()
            _write_library_authorizations(libraries,output,verified["rootDelegation"],release_private_key=release_private_key,public_key=public_key,sidecars_only=True)
            if (read_regular_file_bytes(root_public_key,reject_symlink_parents=True)!=root_bytes
                    or read_regular_file_bytes(keyring,reject_symlink_parents=True)!=policy_bytes
                    or regular_file_inventory(keys_directory)!=policy_inventory
                    or regular_file_inventory(verified["rootDelegation"])!=delegation_inventory):
                raise ValueError("Imported authorization policy changed during signing")
            timings["exactClaimSigning"] = time.monotonic_ns() - scope_started
        inventory=regular_file_inventory(output)
        publish_regular_tree(output,destination,expected_inventory=inventory)
    return {"files":inventory,"sourceTrustDomain":"development","rootFingerprint":public_key_fingerprint(root_bytes),
        "controlSha256":expected_control_sha256,"productPromotion":False,
        "originalProvenance":verified["originalProvenance"],"elapsedNs":time.monotonic_ns()-started,
        "elapsedNsByScope":timings}


def _imported_manifest_files(raw: bytes, control: dict) -> tuple[dict, list[dict]]:
    from products.inventory import require_exact_keys,require_sorted_unique_records,validate_file_record
    if len(raw)!=control["inputManifestBytes"] or sha256_bytes(raw)!=control["inputManifestSha256"]:
        raise ValueError("Imported manifest differs from independently approved bytes")
    value=require_exact_keys(load_canonical_json_bytes(raw),{
        "schemaVersion","kind","files","originals","contractStage","runtimeStageRoot",
        "custodyCheckpoint","compatibilityRequest","rootDelegation","sourceMappings"},"Imported original inventory")
    if value["schemaVersion"]!=1 or type(value["schemaVersion"]) is not int or value["kind"]!=_IMPORTED_KIND:
        raise ValueError("Imported manifest kind/schema differs")
    files=require_sorted_unique_records(value["files"],"Imported files")
    if not 0<len(files)<=16384:raise ValueError("Imported file count exceeds bound")
    for row in files:validate_file_record(row,"Imported file",with_kind=False,allow_empty=True)
    if sum(row["bytes"] for row in files)>4*1024**3 or any(row["bytes"]>1024**3 for row in files):
        raise ValueError("Imported file bytes exceed bound")
    unique={}
    for row in files:
        if row["relativePath"]=="runtime-validation-import.json":raise ValueError("Import manifest cannot inventory itself")
        if row["sha256"] in unique and row["bytes"]!=unique[row["sha256"]]["bytes"]:raise ValueError("Conflicting object length")
        unique[row["sha256"]]=row
    return value,list(unique.values())


def capture_imported_validation_objects(control_path: Path,destination: Path,storage: Path,*,
        expected_control_sha256: str,trusted_source_commit: str) -> dict:
    """Token-only official-repository LFS intake; each exact content object once."""
    started = time.monotonic_ns()
    from concurrent.futures import ThreadPoolExecutor
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    from ci.tests.phase9_ios_mutation import lfs_object,LFS_URL
    from products.signing_isolation import require_no_signing_secret
    require_no_signing_secret(os.environ)
    if _ROOT_SECRET in os.environ or "RELEASE_PRIVATE_KEY" in os.environ:raise ValueError("Capture must not receive signing keys")
    control=validate_imported_validation_control(read_regular_file_bytes(control_path,max_bytes=65536,reject_symlink_parents=True),
        expected_sha256=expected_control_sha256,trusted_source_commit=trusted_source_commit)
    destination,storage=Path(destination).absolute(),Path(storage).absolute()
    if destination.exists() or storage.exists():raise ValueError("Capture/cache must be exclusively new")
    destination.mkdir();storage.mkdir()
    environment=dict(os.environ,GIT_TERMINAL_PROMPT='0',GIT_CONFIG_COUNT='6',
        GIT_CONFIG_KEY_0='lfs.storage',GIT_CONFIG_VALUE_0=str(storage),GIT_CONFIG_KEY_1='lfs.url',GIT_CONFIG_VALUE_1=LFS_URL,
        GIT_CONFIG_KEY_2='credential.helper',GIT_CONFIG_VALUE_2='',GIT_CONFIG_KEY_3='credential.helper',GIT_CONFIG_VALUE_3='!gh auth git-credential',
        GIT_CONFIG_KEY_4='lfs.fetchinclude',GIT_CONFIG_VALUE_4='',GIT_CONFIG_KEY_5='lfs.fetchexclude',GIT_CONFIG_VALUE_5='')
    environment.pop('GIT_LFS_SKIP_SMUDGE',None)
    row=dict(relativePath='runtime-validation-import.json',bytes=control['inputManifestBytes'],sha256=control['inputManifestSha256'])
    manifest,_=lfs_object(row,storage,environment,('git','lfs'))
    raw=read_regular_file_bytes(manifest,max_bytes=16*1024*1024,reject_symlink_parents=True)
    value,unique=_imported_manifest_files(raw,control)
    (destination/'objects').mkdir();(destination/'manifest.json').write_bytes(raw)
    def receive(row):
        source,downloaded=lfs_object(row,storage,environment,('git','lfs'))
        os.link(source,destination/'objects'/row['sha256'][7:])
        return downloaded
    with ThreadPoolExecutor(max_workers=4) as pool:downloaded=sum(pool.map(receive,unique))
    return {'uniqueObjects':len(unique),'downloadedBytes':downloaded,'payloadCopies':0,
        'manifestSha256':control['inputManifestSha256'],'controlSha256':expected_control_sha256,
        'elapsedNs':time.monotonic_ns()-started}


def materialize_imported_validation_objects(capture: Path,destination: Path,control_path: Path,*,
        expected_control_sha256: str,trusted_source_commit: str) -> dict:
    """Validate exact same-run objects, then link only the declared input aliases."""
    started = time.monotonic_ns()
    from products.inventory import require_regular_directory,require_relative_path
    control=validate_imported_validation_control(read_regular_file_bytes(control_path,max_bytes=65536,reject_symlink_parents=True),
        expected_sha256=expected_control_sha256,trusted_source_commit=trusted_source_commit)
    capture,destination=Path(capture).absolute(),Path(destination).absolute()
    require_regular_directory(capture)
    if destination.exists() or destination.is_symlink():raise ValueError("Materialized input directory exists")
    raw=read_regular_file_bytes(capture/'manifest.json',max_bytes=16*1024*1024,reject_symlink_parents=True)
    value,unique=_imported_manifest_files(raw,control)
    expected=[dict(relativePath='manifest.json',bytes=len(raw),sha256=sha256_bytes(raw))]+[
        dict(relativePath='objects/'+row['sha256'][7:],bytes=row['bytes'],sha256=row['sha256']) for row in unique]
    if regular_file_inventory(capture,allow_empty=True)!=sorted(expected,key=lambda row:row['relativePath']):
        raise ValueError("Captured object inventory changed")
    destination.mkdir();(destination/'runtime-validation-import.json').write_bytes(raw)
    for row in value['files']:
        output=destination/require_relative_path(row['relativePath'],'Imported alias')
        output.parent.mkdir(parents=True,exist_ok=True)
        os.link(capture/'objects'/row['sha256'][7:],output)
    return {'objects':len(unique),'aliases':len(value['files']),'payloadCopies':0,
        'elapsedNs':time.monotonic_ns()-started}

def _run_imported_cli(args):
    started, timings = time.monotonic_ns(), {}
    common = dict(expected_control_sha256=args.expected_control_sha256,
                  trusted_source_commit=args.trusted_source_commit)
    try:
        if args.mode == "capture-imported":
            result = capture_imported_validation_objects(Path(args.control), Path(args.destination),
                Path(args.storage), **common)
        elif args.mode == "materialize-imported":
            result = materialize_imported_validation_objects(Path(args.capture), Path(args.destination),
                Path(args.control), **common)
        else:
            result = produce_imported_runtime_libraries(Path(args.directory), Path(args.control),
                Path(args.destination), **common, keyring=Path(args.keyring),
                keys_directory=Path(args.keys_directory), root_public_key=Path(args.root_public_key),
                expected_root_public_key_sha256=args.expected_root_public_key_sha256,
                release_private_key=Path(args.release_private_key), timings=timings)
    except Exception as error:
        print(json.dumps(dict(schemaVersion=1, scope=args.mode, passed=False,
            errorType=type(error).__name__, error=str(error),
            elapsedNs=time.monotonic_ns()-started, elapsedNsByScope=timings), sort_keys=True))
        raise
    result.update(schemaVersion=1, scope=args.mode, passed=True)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Issue split Runtime root and release evidence")
    modes = parser.add_subparsers(dest="mode", required=True)
    delegate = modes.add_parser("delegate")
    for name in ("destination", "keyring", "keys-directory", "root-public-key",
                 "expected-root-public-key-sha256", "expected-keyring-sha256",
                 "expected-keys-inventory-sha256", "root-private-key"):
        delegate.add_argument(f"--{name}", required=True)
    authorize = modes.add_parser("authorize")
    authorize.add_argument("--sidecars-only", action="store_true",
        help="Phase9 validation evidence only; omit already-preserved library bodies")
    for name in ("protected-output", "destination", "expected-metadata-receipt-sha256",
                 "expected-build-key", "keyring", "keys-directory", "root-public-key",
                 "expected-root-fingerprint", "expected-root-public-key-sha256",
                 "root-delegation", "expected-delegation-inventory-sha256", "release-private-key"):
        authorize.add_argument(f"--{name}", required=True)
    imported=modes.add_parser("authorize-imported")
    for name in ("directory","control","destination","expected-control-sha256","trusted-source-commit",
            "keyring","keys-directory","root-public-key","expected-root-public-key-sha256","release-private-key"):
        imported.add_argument("--"+name,required=True)
    for mode in ("capture-imported","materialize-imported"):
        command=modes.add_parser(mode)
        for name in ("control","destination","expected-control-sha256","trusted-source-commit"):
            command.add_argument("--"+name,required=True)
        command.add_argument("--storage" if mode=="capture-imported" else "--capture",required=True)
    args = parser.parse_args(argv)
    if args.mode.endswith("-imported"):
        return _run_imported_cli(args)
    if args.mode == "delegate":
        result = issue_authenticated_runtime_root_delegation(
            Path(args.destination), keyring=Path(args.keyring),
            keys_directory=Path(args.keys_directory), root_public_key=Path(args.root_public_key),
            expected_root_public_key_sha256=args.expected_root_public_key_sha256,
            expected_keyring_sha256=args.expected_keyring_sha256,
            expected_keys_inventory_sha256=args.expected_keys_inventory_sha256,
            root_private_key=Path(args.root_private_key),
        )
    else:
        result = produce_authenticated_runtime_libraries(
            Path(args.protected_output), Path(args.destination),
            expected_metadata_receipt_sha256=args.expected_metadata_receipt_sha256,
            expected_build_key=args.expected_build_key,
            keyring=Path(args.keyring), keys_directory=Path(args.keys_directory),
            root_public_key=Path(args.root_public_key),
            expected_root_fingerprint=args.expected_root_fingerprint,
            expected_root_public_key_sha256=args.expected_root_public_key_sha256,
            root_delegation=Path(args.root_delegation),
            expected_delegation_inventory_sha256=args.expected_delegation_inventory_sha256,
            release_private_key=Path(args.release_private_key),
            sidecars_only=args.sidecars_only,
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
