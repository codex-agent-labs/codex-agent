"""Detached authentication of original Apple validation evidence, not product bytes.

This binding is deliberately provenance-bearing. It does not replace full
source/tooling/semantic replay or authorize a signing operation by itself.
"""

from contextlib import contextmanager
from pathlib import Path
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_integer, require_sha256, sha256_bytes, snapshot_regular_tree,
)
from .receipt import validate_phase_receipt
from .runtime_aggregate_handoff import _public_policy
from .sdk_apple_content import _input_inventory
from .signatures import (
    load_keyring, public_key_for_metadata, validate_signing_metadata, verify_manifest_signature,
)


ATTESTATION_NAME = "apple-validation-attestation.json"
SIGNATURE_NAME = "apple-validation-attestation.sig"
_LIMIT = 16 * 1024 * 1024


def validate_apple_validation_attestation(value):
    value = require_exact_keys(value, {
        "schemaVersion", "product", "component", "phase", "target", "receiptSha256", "captureDigest", "signing",
    }, "Apple validation attestation")
    if (require_integer(value["schemaVersion"], "Apple attestation schema", 1) != 1
            or (value["product"], value["component"], value["phase"]) != ("sdk", "sdk-ios", "validation")
            or value["target"] not in ("ios-arm64", "ios-simulator-arm64")):
        raise ValueError("Apple attestation requires an exact target validation identity")
    require_sha256(value["receiptSha256"], "Apple attestation original receipt")
    require_sha256(value["captureDigest"], "Apple attestation complete capture")
    validate_signing_metadata(value["signing"])
    return value


def derive_apple_validation_attestation(capture, receipt_bytes, signing):
    """Construct binding data only; protected signing still requires full replay."""
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    if ((receipt["product"], receipt["component"], receipt["phase"]) != ("sdk", "sdk-ios", "validation")
            or receipt["target"] not in ("ios-arm64", "ios-simulator-arm64")):
        raise ValueError("Apple evidence binding requires an original target validation receipt")
    capture = Path(capture)
    inventory = _input_inventory(capture, allow_empty=True)
    original = capture / "original/shard/phase-receipt.json"
    if read_regular_file_bytes(original, max_bytes=_LIMIT, reject_symlink_parents=True) != receipt_bytes:
        raise ValueError("Apple evidence capture differs from the selected original receipt")
    value = validate_apple_validation_attestation({
        "schemaVersion": 1, "product": "sdk", "component": "sdk-ios", "phase": "validation",
        "target": receipt["target"], "receiptSha256": sha256_bytes(receipt_bytes),
        "captureDigest": sha256_bytes(canonical_json_bytes(inventory)),
        "signing": validate_signing_metadata(signing),
    })
    if _input_inventory(capture, allow_empty=True) != inventory:
        raise ValueError("Apple evidence capture changed while deriving its binding")
    return value


def verify_apple_validation_binding(capture, receipt_bytes, value):
    """Validate exact byte binding, without inferring signer or semantic trust."""
    value = validate_apple_validation_attestation(value)
    if value != derive_apple_validation_attestation(capture, receipt_bytes, value["signing"]):
        raise ValueError("Apple validation attestation does not bind the exact original capture")


@contextmanager
def verified_apple_validation_attestation(capture, receipt_path, attestation, signature, *,
        public_key, required_trust_domain, keyring=None, keys_directory=None):
    """Hold caller-pinned signer authentication while full replay consumes a copy.

    Development keys must be explicitly pinned by the caller's independently
    authenticated original-upload/local policy. A key from this evidence is not
    a trust root. Release mode requires the caller's tracked keyring and may
    select its exact signed key identity when public_key is None.
    Successful signature verification alone never proves compiler/host behavior.
    """
    if required_trust_domain not in {"development", "release"}:
        raise ValueError("Apple attestation requires an explicit caller trust domain")
    if (required_trust_domain == "release" and (keyring is None or keys_directory is None)
            or required_trust_domain == "development" and (keyring is not None or keys_directory is not None)):
        raise ValueError("Apple attestation trust requires exact caller-pinned key policy")
    if required_trust_domain == "development" and public_key is None:
        raise ValueError("Development Apple attestation requires an explicit caller public key")
    capture = Path(capture)
    files = {"receipt": Path(receipt_path), "attestation": Path(attestation),
             "signature": Path(signature)}
    if public_key is not None:
        files["public-key"] = Path(public_key)
    if files["attestation"].name != ATTESTATION_NAME or files["signature"].name != SIGNATURE_NAME:
        raise ValueError("Apple validation attestation filenames are not canonical")
    # Signatures must never become part of the capture whose digest they bind.
    for name in ("attestation", "signature"):
        if capture.absolute() in files[name].absolute().parents:
            raise ValueError("Apple evidence signature must remain outside its capture")
    originals = {name: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
                 for name, path in files.items()}
    before = canonical_json_bytes(_input_inventory(capture, allow_empty=True))
    value = validate_apple_validation_attestation(load_canonical_json_bytes(originals["attestation"]))
    signing = validate_signing_metadata(value["signing"], trust_domain=required_trust_domain)
    with tempfile.TemporaryDirectory(prefix="apple-validation-attestation-") as temporary:
        root = Path(temporary).resolve()
        captured = root / "capture"
        policy_paths, policy_bytes = {}, {}
        if required_trust_domain == "release":
            policy_paths, policy_bytes = _public_policy(Path(keyring), Path(keys_directory), root / "policy")
            trusted = public_key_for_metadata(signing,
                load_keyring(root / "policy/product-signing-keys.json", root / "policy/keys"),
                root / "policy/keys", allow_retired=True)
            selected_public = read_regular_file_bytes(trusted, reject_symlink_parents=True)
            if public_key is not None and selected_public != originals["public-key"]:
                raise ValueError("Apple attestation public key differs from caller release policy")
            originals["public-key"] = selected_public
        snapshot_regular_tree(capture, captured, allow_empty=True)
        snapshots = {}
        for name, raw in originals.items():
            snapshots[name] = root / name
            snapshots[name].write_bytes(raw)
        verify_manifest_signature(snapshots["attestation"], snapshots["signature"], snapshots["public-key"], signing)
        verify_apple_validation_binding(captured, originals["receipt"], value)

        def unchanged():
            if (canonical_json_bytes(_input_inventory(capture, allow_empty=True)) != before
                    or canonical_json_bytes(_input_inventory(captured, allow_empty=True)) != before
                    or canonical_json_bytes(value) != originals["attestation"]
                    or any(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != originals[name]
                           for name, path in files.items())
                    or any(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != originals[name]
                           for name, path in snapshots.items())
                    or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True) != policy_bytes[name]
                           for name, path in policy_paths.items())):
                raise ValueError("Authenticated Apple evidence or caller policy changed during use")
        unchanged()
        try:
            yield {"capture": captured, "receiptBytes": originals["receipt"], "attestation": value,
                   "attestationBytes": originals["attestation"], "signatureBytes": originals["signature"]}
        finally:
            unchanged()


@contextmanager
def verified_apple_validation_handoff(evidence_root, *, plan, expected_receipt_sha256, target,
        attestation_public_key, attestation_trust_domain, keyring, keys_directory,
        repository_root, tooling_evidence, tooling_public_key, java_executable,
        policy_revision, required_trust_domain, tooling_keyring=None, tooling_keys_directory=None):
    """Authenticate the complete original capture AND replay its full content gate.

    The selected receipt/target and all key policies come from the caller, never
    from a claim in this evidence. No capture is rebuilt or resigned here.
    """
    if __package__ == "ci.products":
        from ..sdk_ios_original_validation import verified_retained_ios_validation
    else:
        from sdk_ios_original_validation import verified_retained_ios_validation
    root = Path(evidence_root)
    require_sha256(expected_receipt_sha256, "Selected Apple validation receipt")
    if target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Apple handoff requires an exact caller-selected target")
    before = canonical_json_bytes(_input_inventory(root, allow_empty=True))
    if {path.name for path in root.iterdir()} != {"capture", ATTESTATION_NAME, SIGNATURE_NAME}:
        raise ValueError("Apple validation handoff contains unexpected files")
    capture = root / "capture"
    with verified_apple_validation_attestation(capture, capture / "original/shard/phase-receipt.json",
            root / ATTESTATION_NAME, root / SIGNATURE_NAME, public_key=attestation_public_key,
            required_trust_domain=attestation_trust_domain,
            keyring=keyring if attestation_trust_domain == "release" else None,
            keys_directory=keys_directory if attestation_trust_domain == "release" else None) as authenticated:
        if (sha256_bytes(authenticated["receiptBytes"]) != expected_receipt_sha256
                or authenticated["attestation"]["target"] != target):
            raise ValueError("Authenticated Apple evidence differs from the caller-selected receipt or target")
        retained = authenticated["capture"]
        try:
            with verified_retained_ios_validation(plan, retained / "original/shard/phase-receipt.json",
                    validation_capture=retained, keyring=keyring, keys_directory=keys_directory,
                    repository_root=repository_root, tooling_evidence=tooling_evidence,
                    tooling_public_key=tooling_public_key, java_executable=java_executable,
                    policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                    tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory) as verified:
                if (verified["receiptBytes"] != authenticated["receiptBytes"]
                        or verified["receipt"]["target"] != target):
                    raise ValueError("Apple replay returned a different original validation receipt")
                yield verified
        finally:
            if canonical_json_bytes(_input_inventory(root, allow_empty=True)) != before:
                raise ValueError("Authenticated Apple handoff changed during full replay")
