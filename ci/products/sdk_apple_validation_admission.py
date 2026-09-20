"""Concrete receipt-bound admission through the complete Apple handoff gate."""

from pathlib import Path
import re

from .inventory import canonical_json_bytes, require_exact_keys, require_string
from .sdk_apple_validation_attestation import verified_apple_validation_handoff
from .sdk_apple_validation_inputs import rebase_sdk_apple_validation_records


_PATHS = {
    "plan": "plan", "attestationPublicKey": "attestation_public_key",
    "keyring": "keyring", "keysDirectory": "keys_directory",
    "toolingEvidence": "tooling_evidence", "toolingPublicKey": "tooling_public_key",
    "javaExecutable": "java_executable", "toolingKeyring": "tooling_keyring",
    "toolingKeysDirectory": "tooling_keys_directory",
}


class AppleValidationAdmission:
    """Run signature AND original semantic replay without caching acceptance.

    The caller owns the selected envelope, repository revision and all policy
    paths. Transported observations and signing metadata cannot select policy.
    Successful return occurs only after the complete handoff context exits.
    """

    def __init__(self, root, records, *, repository, policy_revision, policy):
        if type(policy_revision) is not str or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", policy_revision) is None:
            raise ValueError("Apple admission requires an exact caller policy revision")
        policy = require_exact_keys(policy, {*_PATHS, "attestationTrustDomain", "toolingTrustDomain"},
                                    "Apple validation caller policy")
        for name in ("attestationTrustDomain", "toolingTrustDomain"):
            if type(policy[name]) is not str or policy[name] not in {"development", "release"}:
                raise ValueError("Apple admission requires explicit caller trust domains")
        optional = ("toolingKeyring", "toolingKeysDirectory")
        if (policy["toolingTrustDomain"] == "release" and any(policy[name] is None for name in optional)
                or policy["toolingTrustDomain"] == "development" and any(policy[name] is not None for name in optional)):
            raise ValueError("Apple tooling trust requires the exact caller keyring pair")
        arguments = {}
        for field, name in _PATHS.items():
            if field in optional and policy[field] is None:
                arguments[name] = None
                continue
            path = Path(require_string(policy[field], f"Apple caller {field}"))
            if not path.is_absolute():
                raise ValueError("Apple caller policy paths must be absolute")
            arguments[name] = path
        self._root = Path(root).absolute()
        self._records = {record["receiptSha256"]: record for record in
                         rebase_sdk_apple_validation_records(records, self._root, self._root)}
        self._arguments = {**arguments, "repository_root": Path(repository), "policy_revision": policy_revision,
            "attestation_trust_domain": policy["attestationTrustDomain"],
            "required_trust_domain": policy["toolingTrustDomain"]}

    def verify(self, envelope):
        # Local import preserves the existing envelope validator without an
        # import cycle when the reuse engine constructs this admission object.
        from .reuse import _validate_envelope

        instance, envelope = _validate_envelope(envelope)
        if ((instance.product, instance.component, instance.phase) != ("sdk", "sdk-ios", "validation")
                or instance.target not in ("ios-arm64", "ios-simulator-arm64")):
            raise ValueError("Apple admission requires an exact SDK iOS validation envelope")
        raw, digest = envelope["receiptBytes"], envelope["receiptSha256"]
        record = self._records.get(digest)
        if record is None or record["target"] != instance.target:
            raise ValueError("Apple validation admission lacks the exact original receipt/target evidence")
        with verified_apple_validation_handoff(self._root / record["evidenceRoot"],
                expected_receipt_sha256=digest, target=instance.target, **self._arguments) as verified:
            if verified["receiptBytes"] != raw or canonical_json_bytes(verified["receipt"]) != raw:
                raise ValueError("Apple validation handoff differs from the selected envelope")
        if (envelope["receiptBytes"] != raw or envelope["receiptSha256"] != digest
                or canonical_json_bytes(envelope["receipt"]) != raw
                or verified["receiptBytes"] != raw or canonical_json_bytes(verified["receipt"]) != raw):
            raise ValueError("Apple validation receipt changed before admission completed")
