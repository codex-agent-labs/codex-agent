"""Bind a selected Core/Android Maven object to its full retained original gate.

The caller authenticates the envelope, capture, and every policy input. This
returns original receipt bytes only; it does not attest a host or admit release.
"""

from pathlib import Path
import os
import tempfile

from .inventory import canonical_json_bytes, regular_file_inventory
from .receipt import verify_output_manifest_identity
from .registry import PhaseInstanceId
from .restore import verify_phase_shard
from .sdk_package import _require_capability_output_separate
from .signing_isolation import require_no_signing_secret


_MAVEN = {
    PhaseInstanceId("sdk", component, phase, target)
    for component, target in (("sdk-core", "common"), ("sdk-android", "android"))
    for phase in ("binary", "package")
}


def verify_campaign_maven_phase(
    envelope, stage, capture_root, *, plan, repository_root,
    binary_contract_evidence, original_context, environ=None,
    keyring=None, keys_directory=None, android_runtime_archive=None,
    binary_original_context=None,
) -> bytes:
    """Replay one exact selected original; no producer or policy is inferred."""
    from .reuse import _validate_envelope
    if __package__ == "products":
        from sdk_maven_original import verified_retained_maven_phase
    else:
        from ..sdk_maven_original import verified_retained_maven_phase

    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if environment is not os.environ:
        require_no_signing_secret(os.environ)
    identity, selected = _validate_envelope(envelope)
    if identity not in _MAVEN:
        raise ValueError("Campaign Maven requires an exact Core/Android binary or package envelope")
    stage, capture_root = Path(stage), Path(capture_root)
    plan, repository_root = Path(plan), Path(repository_root)
    before = regular_file_inventory(stage)
    manifest = verify_output_manifest_identity(stage, identity.product, identity.component,
        identity.phase, identity.target, selected["receipt"]["productVersion"])
    if manifest["outputs"] != selected["receipt"]["outputs"]:
        raise ValueError("Campaign Maven selected stage differs from its receipt")
    def binding_of(value):
        _, value = _validate_envelope(value)
        return (value["receiptBytes"], value["receiptSha256"], value["objectSha256"],
                canonical_json_bytes(value["receipt"]))

    binding = binding_of(envelope)

    def unchanged():
        require_no_signing_secret(environment)
        if (regular_file_inventory(stage) != before or binding_of(envelope) != binding):
            raise ValueError("Campaign Maven selected object or stage changed during replay")

    unchanged()
    try:
        with tempfile.TemporaryDirectory(prefix="campaign-maven-original-") as temporary:
            receipt = Path(temporary).resolve() / "phase-receipt.json"
            _require_capability_output_separate(receipt, (stage, capture_root, plan, repository_root))
            receipt.write_bytes(selected["receiptBytes"])
            with verified_retained_maven_phase(
                plan, receipt, capture_root=capture_root,
                binary_contract_evidence=binary_contract_evidence,
                original_context=original_context, repository_root=repository_root,
                environ=environment, keyring=keyring, keys_directory=keys_directory,
                android_runtime_archive=android_runtime_archive,
                binary_original_context=binary_original_context,
            ) as original:
                shard = verify_phase_shard(Path(original["original"]) / "shard", identity)
                if (original["receiptBytes"] != binding[0] or
                        any(shard[name] != expected for name, expected in (
                            ("receiptBytes", binding[0]), ("receiptSha256", binding[1]),
                            ("objectSha256", binding[2]),
                            ("buildKey", selected["receipt"]["buildKey"]))) or
                        regular_file_inventory(Path(original["stage"])) != before):
                    raise ValueError("Campaign Maven original differs from selected object or stage")
                unchanged()
            unchanged()
            if receipt.read_bytes() != binding[0]:
                raise ValueError("Campaign Maven private receipt changed during replay")
    finally:
        unchanged()
    return binding[0]
