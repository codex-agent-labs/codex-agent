"""Concrete Core metadata replay binding, not hardware/toolchain attestation.

The reuse caller authenticates the enclosing carrier and selected object bytes.
This adapter requires the existing complete retained semantic/source/key replay;
partial compiler policies retain their limitations and unsupported-host failures.
Neither records, successful dictionaries nor this class mint a host trust token.
"""

import os
from pathlib import Path
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_array, require_exact_keys, require_relative_path, require_sha256, require_regular_directory,
)
from .receipt import verify_output_manifest_identity
from .restore import verify_phase_shard
from .registry import SDK_FACADE_TARGETS, SDK_FACADE_CONTRACT_COMPONENTS
from .sdk_facade_inputs import _path
from .sdk_facade_validation import _inventory
from .sdk_package import _require_capability_output_separate
from .signing_isolation import require_no_signing_secret
from .toolchain import _revision

_PATHS = {"plan": "plan", "toolingEvidence": "tooling_evidence", "toolingPublicKey": "tooling_public_key",
          "javaExecutable": "java_executable", "toolingKeyring": "tooling_keyring",
          "toolingKeysDirectory": "tooling_keys_directory"}


def _arguments(policy):
    if __package__.startswith("ci."):
        from ..sdk_facade_metadata_inputs import _records
        from ..sdk_facade_metadata_original import _context
    else:
        from sdk_facade_metadata_inputs import _records
        from sdk_facade_metadata_original import _context
    policy = require_exact_keys(policy, {*_PATHS, "validations", "contractDigest", "componentDigests",
                                       "originalContext", "toolingTrustDomain"}, "Core metadata caller policy")
    trust = policy["toolingTrustDomain"]
    if type(trust) is not str or trust not in {"development", "release"}:
        raise ValueError("Core metadata requires an explicit tooling trust domain")
    pair = ("toolingKeyring", "toolingKeysDirectory")
    if any((policy[name] is None) != (trust == "development") for name in pair):
        raise ValueError("Core metadata tooling trust requires the exact caller keyring pair")
    arguments = {name: None if policy[field] is None and field in pair else _path(policy[field], field)
                 for field, name in _PATHS.items()}
    records = _records(policy["validations"])
    if any("captureRoot" not in record for record in records.values()):
        raise ValueError("Core metadata admission requires eleven retained validations")
    components = require_exact_keys(policy["componentDigests"], set(SDK_FACADE_CONTRACT_COMPONENTS.values()),
                                    "Core metadata Contract components")
    for digest in components.values():
        require_sha256(digest, "Core metadata Contract component digest")
    return {**arguments, "validations": records,
            "contract_digest": require_sha256(policy["contractDigest"], "Core metadata Contract digest"),
            "component_digests": components, "original_context": _context(policy["originalContext"]),
            "required_trust_domain": trust}


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)


class FacadeMetadataAdmission:
    """Replay each selected original anew; only return after every context exits.

    Records are caller-projected receipt locators, never transported policy.
    The repository, policy revision and original contexts are independently
    supplied by the caller. No acceptance cache or success callback exists.
    """

    def __init__(self, root, records, *, repository, policy_revision, policy):
        if __package__.startswith("ci."):
            from ..sdk_facade_metadata_inputs import _view
        else:
            from sdk_facade_metadata_inputs import _view
        self._root = _path(str(root), "Core evidence root")
        self._repository = _path(str(repository), "Core policy repository")
        require_regular_directory(self._root, "Core evidence root")
        require_regular_directory(self._repository, "Core policy repository")
        self._revision = _revision(policy_revision)
        self._policy, self._records = policy, records
        self._policy_bytes, self._record_bytes = canonical_json_bytes(policy), canonical_json_bytes(records)
        self._arguments = _arguments(load_canonical_json_bytes(self._policy_bytes))
        self._arguments_bytes = _view(self._arguments)
        self._captures = {}
        for record in require_array(records, "Core metadata receipt locators"):
            require_exact_keys(record, {"receiptSha256", "captureRoot"}, "Core metadata receipt locator")
            digest = require_sha256(record["receiptSha256"], "Core metadata receipt digest")
            relative = require_relative_path(record["captureRoot"], "Core metadata capture locator")
            capture = _path(str(self._root / relative), "Core metadata retained capture")
            require_regular_directory(capture, "Core metadata retained capture")
            if self._root not in capture.parents or digest in self._captures:
                raise ValueError("Core metadata captures must be confined and receipt-unique")
            self._captures[digest] = capture
        if list(self._captures) != sorted(self._captures):
            raise ValueError("Core metadata receipt locators must be sorted")

    def verify_metadata(self, envelope, validation_envelopes):
        from .reuse import _validate_envelope
        # CI contexts import the reuse engine too; defer until module loading
        # has completed rather than creating a partially initialized cycle.
        if __package__.startswith("ci."):
            from ..sdk_facade_metadata_inputs import _view
            from ..sdk_facade_metadata_original import verified_retained_sdk_facade_metadata
        else:
            from sdk_facade_metadata_inputs import _view
            from sdk_facade_metadata_original import verified_retained_sdk_facade_metadata

        require_no_signing_secret(os.environ)
        instance, envelope = _validate_envelope(envelope)
        if (instance.product, instance.component, instance.phase, instance.target) != ("sdk", "sdk-core", "metadata", "common"):
            raise ValueError("Core metadata admission requires its exact metadata envelope")
        capture = self._captures.get(envelope["receiptSha256"])
        if capture is None:
            raise ValueError("Core metadata admission lacks its exact receipt-bound capture")

        def binding(value):
            _, value = _validate_envelope(value)
            return (value["receiptBytes"], value["receiptSha256"], value["objectSha256"], canonical_json_bytes(value["receipt"]))

        selected = [(envelope, binding(envelope))]
        if not isinstance(validation_envelopes, (list, tuple)):
            raise ValueError("Core metadata predecessors must be an explicit sequence")
        predecessor_ids = tuple(map(id, validation_envelopes))
        originals = {}
        predecessors = {}
        for value in validation_envelopes:
            identity, value = _validate_envelope(value)
            if ((identity.product, identity.component, identity.phase) != ("sdk", "sdk-core", "validation")
                    or identity.target not in SDK_FACADE_TARGETS or identity.target in originals):
                raise ValueError("Core metadata requires exact unique validation predecessors")
            originals[identity.target] = value["receiptBytes"]
            predecessors[identity] = value
            selected.append((value, binding(value)))
        if set(originals) != set(SDK_FACADE_TARGETS):
            raise ValueError("Core metadata requires all eleven validation predecessors")
        receipt_files = {Path(self._arguments["validations"][target]["validationReceipt"]): raw
                         for target, raw in originals.items()}
        if len(receipt_files) != len(SDK_FACADE_TARGETS) or any(_read(path) != raw for path, raw in receipt_files.items()):
            raise ValueError("Core caller validation receipts differ from selected predecessors")
        capture_before = _inventory(capture, allow_empty=True)
        predecessor_captures = {}
        for identity, value in predecessors.items():
            retained = Path(self._arguments["validations"][identity.target]["captureRoot"])
            predecessor_captures[retained] = _inventory(retained, allow_empty=True)
            shard = verify_phase_shard(retained / "original/shard", identity)
            if any(shard[key] != value[key] for key in ("receiptBytes", "receiptSha256", "objectSha256")):
                raise ValueError("Core validation predecessor object differs from the selected envelope")

        def unchanged():
            require_no_signing_secret(os.environ)
            if (canonical_json_bytes(self._policy) != self._policy_bytes
                    or _view(self._arguments) != self._arguments_bytes
                    or canonical_json_bytes(self._records) != self._record_bytes
                    or tuple(map(id, validation_envelopes)) != predecessor_ids
                    or any(binding(value) != before for value, before in selected)
                    or any(_read(path) != raw for path, raw in receipt_files.items())
                    or any(_inventory(path, allow_empty=True) != before
                           for path, before in predecessor_captures.items())
                    or _inventory(capture, allow_empty=True) != capture_before):
                raise ValueError("Core metadata selected envelopes, capture or caller policy changed")

        unchanged()
        raw = envelope["receiptBytes"]
        try:
            with tempfile.TemporaryDirectory(prefix="core-metadata-admission-") as temporary:
                private = Path(temporary).resolve()
                paths = [self._root, self._repository, *receipt_files,
                         *(value for value in self._arguments.values() if isinstance(value, Path))]
                paths.extend(Path(record[field]) for record in self._arguments["validations"].values()
                             for field in ("captureRoot", "facadeRequest", "nativeCompilerArchive") if field in record)
                _require_capability_output_separate(private, paths)
                receipt_path = private / "metadata-receipt.json"
                receipt_path.write_bytes(raw)
                with verified_retained_sdk_facade_metadata(metadata_receipt_path=receipt_path, capture_root=capture,
                        repository_root=self._repository, policy_revision=self._revision, environ=os.environ,
                        **self._arguments) as verified:
                    if (verified["receiptBytes"] != raw or canonical_json_bytes(verified["receipt"]) != raw
                            or _read(verified["receiptPath"]) != raw):
                        raise ValueError("Core metadata replay returned a different selected receipt")
                    manifest = verify_output_manifest_identity(verified["stage"], "sdk", "sdk-core", "metadata",
                                                               "common", envelope["receipt"]["productVersion"])
                    if manifest["outputs"] != envelope["receipt"]["outputs"]:
                        raise ValueError("Core metadata replay outputs differ from the selected envelope")
                    shard = verify_phase_shard(Path(verified["original"]) / "shard", instance)
                    if (shard["receiptBytes"] != raw or shard["objectSha256"] != envelope["objectSha256"]
                            or shard["receiptSha256"] != envelope["receiptSha256"]):
                        raise ValueError("Core metadata replay object differs from the selected envelope")
                    verified_before = _view(verified)
                    unchanged()
                if _view(verified) != verified_before or _read(receipt_path) != raw:
                    raise ValueError("Core metadata replay changed before its clean exit")
                unchanged()
        finally:
            unchanged()
