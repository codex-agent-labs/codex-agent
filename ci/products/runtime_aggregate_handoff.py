"""Read complete original aggregate caller evidence under caller-pinned trust.

The release signature authenticates product receipts/content, not the unsigned
caller, selection or historical HTTP observations retained alongside them. This
reader does not elect current state, sign, contact CI, or rebuild an aggregate.
"""

from contextlib import contextmanager
from pathlib import Path
import tempfile

from .aggregate import verify_runtime_aggregate_artifacts
from .contract_projection import verify_contract_component_projection
from .inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_regular_directory, sha256_bytes, sha256_file,
    snapshot_regular_tree, verified_zip_contents,
)
from .receipt import verify_output_manifest_identity
from .registry import NATIVE_TARGETS, PhaseInstanceId
from .restore import verify_phase_shard
from .runtime_aggregate import _adapter_receipt_identities
from .runtime_attestation import read_runtime_variant_handoff
from .sdk_runtime_content import verify_native_runtime_validation_content
from .signatures import load_keyring, public_key_path


def _json(path):
    return load_canonical_json_bytes(read_regular_file_bytes(
        path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))


def _public_policy(keyring, keys_directory, destination):
    """Capture declared public files only; the caller supplies the authority."""
    if keyring is None or keys_directory is None:
        raise ValueError("Aggregate release handoff requires caller-pinned public policy")
    policy = load_keyring(keyring, keys_directory)
    paths = {"product-signing-keys.json": Path(keyring)}
    for record in ([policy["activeKey"]] if policy["activeKey"] else []) + policy["retiredKeys"]:
        paths[f"keys/{record['keyId']}.pub"] = public_key_path(keys_directory, record["keyId"])
    originals = {name: read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
                 for name, path in paths.items()}
    for name, raw in originals.items():
        output = destination / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
    (destination / "keys").mkdir(exist_ok=True)
    load_keyring(destination / "product-signing-keys.json", destination / "keys")
    return paths, originals


def _verify_captured(root, keyring, keys_directory):
    # The protected caller later imports this module for reuse. No top-level
    # caller import, second selector, or alternate receipt schema is necessary.
    from runtime_aggregate_release import _selected_originals
    from runtime_aggregate_phase import collect_finalized_inputs
    from product_reuse import _CATALOG_ZIP_LIMITS

    expected = set()

    def file(path):
        expected.add(path.relative_to(root).as_posix())

    def tree(path, *, allow_empty=False):
        records = regular_file_inventory(path, allow_empty=allow_empty)
        expected.update((path / record["relativePath"]).relative_to(root).as_posix() for record in records)
        return records

    caller = _json(root / "caller.json")
    require_exact_keys(caller, {"schemaVersion", "target", "trustedSourceCommit", "trustedSourceTree",
        "trustedWorkflowSha", "transportProducer", "authorizationReason", "event", "environment",
        "metadataReceiptSha256"}, "Original aggregate caller record")
    if type(caller["schemaVersion"]) is not int or caller["schemaVersion"] != 1 or caller["target"] != "aggregate":
        raise ValueError("Original aggregate caller identity is invalid")
    file(root / "caller.json")
    selected = root / "selected-inputs"
    selection = _json(selected / "selection.json")
    originals = _selected_originals(selected, selection, caller["transportProducer"], selection["metadata"]["buildKey"])
    file(selected / "selection.json")
    receipts, receipt_bytes = {}, {}
    for identity, original in originals.items():
        receipt = original["receipt"]
        outputs = verify_output_manifest_identity(original["stage"], *identity, receipt["productVersion"])["outputs"]
        if outputs != receipt["outputs"]:
            raise ValueError("Aggregate retained stage differs from its original receipt")
        tree(original["stage"])
        file(original["receiptPath"])
        instance = PhaseInstanceId(*identity)
        receipts[instance] = receipt
        receipt_bytes[instance] = read_regular_file_bytes(original["receiptPath"], reject_symlink_parents=True)

    def original(component, phase, target):
        return originals[("runtime", component, phase, target)]

    aggregate = original("runtime-aggregate", "metadata", "aggregate")
    records = collect_finalized_inputs(aggregate["stage"], aggregate["receiptPath"], selection["contractVersion"], original)
    if records["manifest"].relative_to(selected).as_posix() != selection["aggregateManifest"]:
        raise ValueError("Aggregate retained manifest differs from its original selection")
    contract = originals[("contract", "contract", "metadata", "common")]
    version = selection["contractVersion"]
    if contract["receipt"]["productVersion"] != version:
        raise ValueError("Retained Contract version differs from its original receipt")
    handoff = selected / "contract-input"
    stem = f"codex-agent-contract-{version}"
    contract_args = dict(contract_payload=handoff / f"{stem}.zip", contract_metadata_receipt=contract["receiptPath"],
        contract_attestation=handoff / f"{stem}.attestation.json",
        contract_attestation_signature=handoff / f"{stem}.attestation.sig", contract_public_key=handoff / "public-key.pub")
    for name in (f"{stem}.zip", f"{stem}.attestation.json", f"{stem}.attestation.sig", "public-key.pub"):
        file(handoff / name)
    tree(handoff / "execution-closure")  # Existing full Contract gate enforces its exact manifest/inventory.
    for phase in ("binary", "package", "validation", "metadata"):
        if read_regular_file_bytes(handoff / f"execution-closure/receipts/{phase}.json") != \
                receipt_bytes[PhaseInstanceId("contract", "contract", phase, "common")]:
            raise ValueError("Retained Contract handoff changes an original receipt")

    def transported_policy(path):
        # Validate public-only transport shape; NEVER use it for verification.
        policy = load_keyring(path / "product-signing-keys.json", path / "keys")
        file(path / "product-signing-keys.json")
        for record in ([policy["activeKey"]] if policy["activeKey"] else []) + policy["retiredKeys"]:
            file(public_key_path(path / "keys", record["keyId"]))

    transported_policy(root / "trust")
    if (selected / "trust").exists():
        transported_policy(selected / "trust")
    signatures = {name: {} for name in ("variant_attestations", "variant_attestation_signatures", "variant_public_keys")}
    for target in NATIVE_TARGETS:
        native = root / "variant-inputs" / target
        verified = read_runtime_variant_handoff(native, target=target, keyring=keyring, keys_directory=keys_directory)
        tree(native)
        if (any(verified["receiptBytes"][phase] != path.read_bytes()
                for phase, path in records["variant_phase_receipts"][target].items())
                or verified["files"][verified["attestation"]["payload"]["fileName"]] != records["variant_bundles"][target].read_bytes()
                or verified["files"]["validation-evidence.json"] != records["variant_validation_evidence"][target].read_bytes()):
            raise ValueError("Retained native handoff differs from original aggregate inputs")
        payload_stem = Path(verified["attestation"]["payload"]["fileName"]).stem
        signatures["variant_attestations"][target] = native / f"{payload_stem}.attestation.json"
        signatures["variant_attestation_signatures"][target] = native / f"{payload_stem}.attestation.sig"
        signatures["variant_public_keys"][target] = native / "public-key.pub"
        projection = verify_contract_component_projection(contract["stage"], contract["receiptPath"],
            contract_args["contract_attestation"], contract_args["contract_attestation_signature"],
            contract_args["contract_public_key"], expected_trust_domain="release", expected_contract_version=version,
            required_components=("common", target), keyring=keyring, keys_directory=keys_directory)
        for phase in ("package", "validation"):
            staged = root / "runtime-stages" / target / phase
            if tree(staged) != regular_file_inventory(original(target, phase, target)["stage"]):
                raise ValueError("Retained native raw stage differs from selected original")
        verify_native_runtime_validation_content(target, root / "runtime-stages", records["variant_phase_receipts"][target],
            records["variant_bundles"][target], signatures["variant_attestations"][target],
            signatures["variant_attestation_signatures"][target], signatures["variant_public_keys"][target],
            projection, contract_args["contract_payload"], required_trust_domain="release",
            keyring=keyring, keys_directory=keys_directory)

    retained = root / "aggregate-input"
    runtime_version = aggregate["receipt"]["productVersion"]
    manifest = records.pop("manifest")
    metadata = records.pop("metadata_receipt")
    attestation_path = retained / f"codex-agent-runtime-{runtime_version}.attestation.json"
    signature = retained / f"codex-agent-runtime-{runtime_version}.attestation.sig"
    public_key = retained / "public-key.pub"
    for path in (attestation_path, signature, public_key, retained / manifest.name, retained / "metadata-receipt.json"):
        file(path)
    if (read_regular_file_bytes(retained / manifest.name) != read_regular_file_bytes(manifest)
            or read_regular_file_bytes(retained / "metadata-receipt.json") != read_regular_file_bytes(metadata)
            or caller["metadataReceiptSha256"] != sha256_file(metadata)):
        raise ValueError("Retained aggregate handoff differs from exact original payload/receipt")
    value = verify_runtime_aggregate_artifacts(manifest, aggregate_metadata_receipt=metadata,
        aggregate_attestation=attestation_path, aggregate_attestation_signature=signature, aggregate_public_key=public_key,
        **records, **contract_args, **signatures, required_trust_domain="release",
        contract_keyring=keyring, contract_keys_directory=keys_directory,
        variant_keyring=keyring, variant_keys_directory=keys_directory,
        aggregate_keyring=keyring, aggregate_keys_directory=keys_directory)

    # Historical observations are preserved, not promoted to fresh API authority.
    # Their original ZIP members must nevertheless equal the retained extraction
    # and exact signed phase receipt, so forwarding cannot replace original data.
    proof_path = root / "original-evidence/transport/original-ci-phases.json"
    proof = require_exact_keys(_json(proof_path), {"target", "observed", "artifacts", "receiptSha256s"},
                               "Original aggregate transport evidence")
    file(proof_path)
    identities = [*_adapter_receipt_identities(), ("runtime-aggregate", "metadata", "aggregate")]
    names = {"-".join(identity) for identity in identities}
    require_exact_keys(proof["artifacts"], names, "Original aggregate artifacts")
    require_exact_keys(proof["receiptSha256s"], names, "Original aggregate receipt digests")
    if proof["target"] != "aggregate" or not isinstance(proof["observed"], list) or not proof["observed"]:
        raise ValueError("Original aggregate transport context is incomplete")
    for identity in identities:
        name = "-".join(identity)
        directory = root / "original-evidence/phases" / name
        archive = directory / "transport.zip"
        zipped, _, archive_record = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
                                                         **_CATALOG_ZIP_LIMITS)
        if (zipped != tree(directory / "original", allow_empty=True)
                or archive_record["sha256"] != proof["artifacts"][name].get("digest")
                or archive_record["bytes"] != proof["artifacts"][name].get("size_in_bytes")):
            raise ValueError("Original aggregate upload/extraction inventory differs")
        file(archive)
        instance = PhaseInstanceId("runtime", *identity)
        shard = verify_phase_shard(directory / "original/shard", instance)
        if shard["receiptBytes"] != receipt_bytes[instance] or proof["receiptSha256s"][name] != sha256_bytes(receipt_bytes[instance]):
            raise ValueError("Original aggregate transport changes a signed original receipt")
    current = root / "selected-state-transport"
    if current.exists():
        transport = _json(current / "capture-transport.json")
        keys = {"artifact", "captureProducer", "observed"}
        require_exact_keys(transport, keys | ({"stateWave"} if "stateWave" in transport else set()), "Original state transport")
        wave = transport.get("stateWave", 0)
        if type(wave) is not int or not 0 <= wave <= 4 or transport["captureProducer"] != caller["transportProducer"]:
            raise ValueError("Retained current transport differs from original caller")
        required = {"product-resume-inputs", "product-resume-state"} | ({"runtime-state"} if wave else set())
        if {path.name for path in (current / "original").iterdir()} != required:
            raise ValueError("Retained current transport has unexpected original directories")
        tree(current / "original", allow_empty=True)
        file(current / "capture-transport.json")
    inventory = regular_file_inventory(root, allow_empty=True)
    if {record["relativePath"] for record in inventory} != expected:
        raise ValueError("Aggregate handoff contains missing or unexpected files")
    return {"manifest": value, "attestation": _json(attestation_path), "receipts": receipts,
            "receiptBytes": receipt_bytes, "inventory": inventory}


@contextmanager
def verified_runtime_aggregate_handoff(root: Path, *, keyring: Path, keys_directory: Path):
    """Yield only a private full-gate capture; recheck inputs on context exit.

    The caller compares these exact original receipts with its selected current
    closure and copies `directory` while this context is open. Retired release
    keys are valid through the existing signature policy; transported policy is
    never substituted for the caller's pin. No signing or network is performed.
    """
    root = Path(root).absolute()
    for path in (root, *root.parents):
        require_regular_directory(path, "Aggregate handoff ancestry")
    roots = {"aggregate-input", "caller.json", "original-evidence", "runtime-stages", "selected-inputs",
             "trust", "variant-inputs"}
    names = {path.name for path in root.iterdir()}
    if names not in (roots, roots | {"selected-state-transport"}):
        raise ValueError("Aggregate handoff requires its exact direct original carrier layout")
    before = regular_file_inventory(root, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="runtime-aggregate-handoff-") as temporary:
        private = Path(temporary).resolve()
        paths, policy_bytes = _public_policy(keyring, keys_directory, private / "policy")
        policy_inventory = regular_file_inventory(private / "policy")
        captured = private / "handoff"
        snapshot_regular_tree(root, captured, allow_empty=True)
        if regular_file_inventory(captured, allow_empty=True) != before:
            raise ValueError("Aggregate handoff changed during capture")
        value = _verify_captured(captured, private / "policy/product-signing-keys.json", private / "policy/keys")

        def unchanged():
            if ({path.name for path in root.iterdir()} != names
                    or {path.name for path in captured.iterdir()} != names
                    or regular_file_inventory(root, allow_empty=True) != before
                    or regular_file_inventory(captured, allow_empty=True) != before
                    or regular_file_inventory(private / "policy") != policy_inventory
                    or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True) != policy_bytes[name]
                           for name, path in paths.items())):
                raise ValueError("Original or captured aggregate handoff/policy changed during verification")

        unchanged()
        yield {**value, "directory": captured}
        unchanged()
